"""FastAPI REST API — 外部驱动 Story Studio 的 JobRunner。

端点：
- POST   /novels            提交新小说 job
- GET    /novels            列出所有 job
- GET    /novels/{id}       查看单个 job 状态
- GET    /novels/{id}/chapters/{n}  读取某章节正文
- POST   /novels/{id}/revise  触发某 job 重写指定章节
- DELETE /novels/{id}       取消/删除 job
- GET    /health            健康检查

启动：python -m api  或  uvicorn api:app --reload
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 确保项目根在 sys.path（api.py 可能被 uvicorn 直接加载）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from jobs import (
    JobRunner,
    JOB_RUNNING,
    JOB_QUEUED,
    JOB_SUCCEEDED,
    JOB_FAILED,
    JOB_RECOVERABLE,
    make_on_progress,
    finalize_job_after_run_all,
)

logger = logging.getLogger(__name__)

# ── 全局 JobRunner（lazy 初始化）──────────────────────────────
_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        cfg = load_config()
        base_dir = os.environ.get("STORY_STUDIO_JOBS_DIR", "jobs")
        _runner = JobRunner(base_dir=base_dir, cfg=cfg, max_concurrent=2)
    return _runner


async def _build_orch_for_job(job):
    """为指定 job 构造独立的 StoryOrchestrator + LLMClient。

    调用方必须在 finally 中 await client.aclose() 释放连接池，
    否则会泄漏 httpx.AsyncClient。返回 (orch, client)。
    """
    from orchestrator import StoryOrchestrator
    from agents.llm_client import LLMClient
    import copy

    runner = get_runner()
    cfg = copy.deepcopy(runner.cfg)
    cfg.knowledge_dir = job.knowledge_dir
    cfg.output_dir = job.output_dir
    client = LLMClient(
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        default_model=cfg.main_model,
    )
    orch = StoryOrchestrator(cfg, client=client)
    if job.project_name:
        orch.project_name = job.project_name
    return orch, client


app = FastAPI(title="Story Studio API", version="1.0")


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """X-API-Key 鉴权中间件。

    仅当 cfg.api_key 非空时启用。/health 与 docs 始终开放；其余端点要求
    请求头 X-API-Key 匹配，否则返回 401。未配置 api_key 时全开放（本地/内网）。

    P1 修复：原代码每请求调 load_config()（读 .env + 解析 YAML + mkdir），
    高并发下文件系统 syscalls 风暴。改为从已缓存的 JobRunner.cfg 读取。
    """
    # 从缓存的 runner 读取 api_key，避免每请求重跑 load_config（P1 修复）
    expected = get_runner().cfg.api_key
    if not expected:
        return await call_next(request)
    path = request.url.path
    if path in ("/health", "/", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)
    provided = request.headers.get("X-API-Key", "")
    if provided != expected:
        return JSONResponse(status_code=401, content={"detail": "invalid or missing X-API-Key"})
    return await call_next(request)


# ── 请求/响应模型 ────────────────────────────────────────────


class NovelCreate(BaseModel):
    brief: str = Field(..., description="创作需求/企划描述")
    project_name: str = Field("", description="项目名（书名）")
    total_chapters: int | None = Field(None, description="目标章节数", ge=1, le=200)
    write_mode: str = Field("sequential", description="写作模式：sequential 逐章串行 / batch 批次并行")


class NovelRevise(BaseModel):
    chapter: int = Field(..., description="要重写的章节号", ge=1)


class BatchWrite(BaseModel):
    start_chapter: int = Field(..., description="起始章节号", ge=1)
    count: int = Field(..., description="本批次章节数", ge=1, le=20)


# ── 端点 ──────────────────────────────────────────────────────


@app.post("/novels")
async def create_novel(req: NovelCreate):
    """提交一个新小说生成任务。"""
    runner = get_runner()
    job_id = await runner.submit(
        brief=req.brief,
        project_name=req.project_name,
        total_chapters=req.total_chapters,
        write_mode=req.write_mode,
    )
    return {"job_id": job_id, "status": "queued"}


@app.get("/novels")
async def list_novels():
    """列出所有小说任务。"""
    runner = get_runner()
    return {"novels": [j.to_dict() for j in runner.list()]}


@app.get("/novels/{job_id}")
async def get_novel(job_id: str):
    """查看单个小说任务状态。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.get("/novels/{job_id}/chapters/{chapter_num}")
async def get_chapter(job_id: str, chapter_num: int):
    """读取某章节正文。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # 从 job 的 knowledge_dir 读章节
    chapter_path = Path(job.knowledge_dir) / "story" / "chapters" / f"chapter_{chapter_num:03d}.md"
    if not chapter_path.exists():
        raise HTTPException(status_code=404, detail=f"chapter {chapter_num} not found")
    return {"chapter": chapter_num, "content": chapter_path.read_text(encoding="utf-8")}


@app.post("/novels/{job_id}/revise")
async def revise_chapter(job_id: str, req: NovelRevise):
    """触发某 job 重写指定章节（仅当 job 已完成或运行中）。

    注意：当前实现是同步重写并返回结果；若 job 仍在运行则拒绝。
    """
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == JOB_RUNNING or job.status == JOB_QUEUED:
        raise HTTPException(status_code=409, detail="job still running, cannot revise")

    orch, client = await _build_orch_for_job(job)
    try:
        result = await orch.phase_writing(req.chapter)
        return {"chapter": req.chapter, "result": result[:1000]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.aclose()


@app.post("/novels/{job_id}/batch")
async def batch_write(job_id: str, req: BatchWrite):
    """触发某 job 的批次并行写作（预协调简报 → 并行写作 → 融合门）。

    仅当 job 不在运行队列中时可调用。
    """
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == JOB_RUNNING or job.status == JOB_QUEUED:
        raise HTTPException(status_code=409, detail="job still running, cannot batch write")

    orch, client = await _build_orch_for_job(job)
    try:
        result = await orch.phase_writing_batch(req.start_chapter, req.count)
        return {
            "start_chapter": req.start_chapter,
            "count": req.count,
            "result": result[:2000],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.aclose()


@app.delete("/novels/{job_id}")
async def cancel_novel(job_id: str):
    """取消/删除一个小说任务。"""
    runner = get_runner()
    ok = await runner.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found or already finished")
    return {"job_id": job_id, "status": "cancelled"}


# ── 任务清单端点（TaskPlanner）─────────────────────────────────

async def _build_planner_for_job(job_id: str):
    """为指定 job 构造 TaskPlanner（复用其 knowledge_dir / cfg）。

    返回 (planner, orch, job, client)。调用方必须在 finally 中
    await client.aclose() 释放连接池。
    """
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from planner import TaskPlanner

    orch, client = await _build_orch_for_job(job)
    planner = TaskPlanner(
        orch, orch.knowledge, orch.cfg, orch.worklog,
        plan_path=Path(job.knowledge_dir) / "task_plan.json",
    )
    return planner, orch, job, client


@app.get("/novels/{job_id}/tasks")
async def get_tasks(job_id: str):
    """返回该 job 的任务清单。"""
    planner, _orch, job, client = await _build_planner_for_job(job_id)
    try:
        plan = planner.load_plan()
        if plan is None:
            return {"job_id": job_id, "plan": None, "message": "尚未生成任务清单"}
        return {
            "job_id": job_id,
            "plan": plan.to_dict(),
            "summary": planner.summary(),
        }
    finally:
        await client.aclose()


@app.post("/novels/{job_id}/tasks/{task_n}/run")
async def run_task(job_id: str, task_n: int):
    """执行该 job 的第 N 个任务（1-based）。"""
    planner, _orch, job, client = await _build_planner_for_job(job_id)
    runner = get_runner()
    # per-job 锁：防止与 _run_job / run_all 并发编排同一 knowledge_dir（P0 修复）
    async with runner._get_job_lock(job_id):
        try:
            if job.status == JOB_RUNNING or job.status == JOB_QUEUED:
                raise HTTPException(status_code=409, detail="job still running")
            plan = planner.load_plan()
            if plan is None:
                raise HTTPException(status_code=404, detail="task plan not found, POST /novels first")
            task = next((t for t in plan.tasks if t.id == task_n), None)
            if task is None:
                raise HTTPException(status_code=404, detail=f"task #{task_n} not found")
            if task.status in ("done", "running"):
                planner.reset_task(task_n)
                task = next((t for t in planner.plan.tasks if t.id == task_n), task)
            # H4 修复：单任务执行也更新 job 状态，便于前端轮询
            job.status = JOB_RUNNING
            job.phase = task.phase
            runner._save_index()
            try:
                result = await planner.run_task(task)
                job.status = JOB_SUCCEEDED
                job.touch()
                runner._save_index()
                return {"task_id": task_n, "status": task.status, "result": result[:1000]}
            except Exception as e:
                job.status = JOB_FAILED
                job.error = str(e)
                job.touch()
                runner._save_index()
                raise HTTPException(status_code=500, detail=str(e))
        finally:
            await client.aclose()


@app.post("/novels/{job_id}/run-all")
async def run_all_tasks(job_id: str):
    """按序执行该 job 的所有未完成任务。"""
    planner, orch, job, client = await _build_planner_for_job(job_id)
    runner = get_runner()
    # per-job 锁：防止与 _run_job / run_task 并发编排同一 knowledge_dir（P0 修复）
    async with runner._get_job_lock(job_id):
        try:
            if job.status == JOB_RUNNING or job.status == JOB_QUEUED:
                raise HTTPException(status_code=409, detail="job still running")
            if planner.load_plan() is None:
                raise HTTPException(status_code=404, detail="task plan not found")
            # H4 修复：显式标记 running，run_all 期间 on_progress 持续更新 phase/progress
            job.status = JOB_RUNNING
            job.touch()
            runner._save_index()
            _on_progress = make_on_progress(
                job, planner, orch, on_save=runner._save_index
            )
            try:
                await planner.run_all(on_progress=_on_progress, stop_on_failure=True)
            except Exception as e:
                job.status = JOB_FAILED
                job.error = str(e)
                job.touch()
                runner._save_index()
                raise HTTPException(status_code=500, detail=str(e))
            # H6 修复：根据 planner.summary 判定 job 状态（run_all 吞了异常，需显式检查）
            s = planner.summary()
            if s.get("failed", 0) > 0:
                # 部分失败：标记 job failed 但返回 200 + partial_failure（便于前端展示哪些 task 失败）
                job.status = JOB_FAILED
                failed_tasks = [
                    f"#{t.id}({t.phase})" for t in planner.plan.tasks if t.status == "failed"
                ]
                job.error = f"任务失败 {s['failed']} 个：{', '.join(failed_tasks)}"
                job.touch()
                runner._save_index()
                return {
                    "job_id": job_id,
                    "status": "partial_failure",
                    "summary": s,
                    "failed_tasks": [
                        {"id": t.id, "phase": t.phase, "error": t.error}
                        for t in planner.plan.tasks if t.status == "failed"
                    ],
                }
            # 全部成功：填充 result
            finalize_job_after_run_all(job, planner, orch, fallback_total=0)
            runner._save_index()
            return {"job_id": job_id, "status": "succeeded", "summary": s}
        finally:
            await client.aclose()


@app.post("/novels/{job_id}/resume")
async def resume_novel(job_id: str):
    """手动恢复一个 failed/recoverable 的 job，从已有 task_plan.json 断点续跑。

    与 run-all 的区别：resume 专用于崩溃后恢复，强制走 load_plan（不 build_plan），
    并明确校验 task_plan.json 存在。自动恢复（_auto_recover_jobs）已覆盖大多数
    场景，此端点给用户手动控制权。
    """
    planner, orch, job, client = await _build_planner_for_job(job_id)
    runner = get_runner()
    async with runner._get_job_lock(job_id):
        try:
            if job.status not in (JOB_FAILED, JOB_RECOVERABLE, JOB_SUCCEEDED):
                raise HTTPException(
                    status_code=409,
                    detail=f"job status {job.status} cannot resume (only failed/recoverable/succeeded)",
                )
            # 强制 load_plan（断点续跑），无 plan 则无法恢复
            existing = planner.load_plan()
            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail="no task_plan.json to resume from, POST /novels first",
                )
            job.status = JOB_RUNNING
            job.error = None
            job.touch()
            runner._save_index()
            _on_progress = make_on_progress(
                job, planner, orch, on_save=runner._save_index
            )
            try:
                await planner.run_all(on_progress=_on_progress, stop_on_failure=True)
            except Exception as e:
                job.status = JOB_FAILED
                job.error = str(e)
                job.touch()
                runner._save_index()
                raise HTTPException(status_code=500, detail=str(e))
            s = planner.summary()
            if s.get("failed", 0) > 0:
                job.status = JOB_FAILED
                failed_tasks = [
                    f"#{t.id}({t.phase})" for t in planner.plan.tasks if t.status == "failed"
                ]
                job.error = f"恢复后任务失败 {s['failed']} 个：{', '.join(failed_tasks)}"
                job.touch()
                runner._save_index()
                return {
                    "job_id": job_id,
                    "status": "partial_failure",
                    "summary": s,
                    "failed_tasks": [
                        {"id": t.id, "phase": t.phase, "error": t.error}
                        for t in planner.plan.tasks if t.status == "failed"
                    ],
                }
            finalize_job_after_run_all(job, planner, orch, fallback_total=0)
            runner._save_index()
            return {"job_id": job_id, "status": "succeeded", "summary": s}
        finally:
            await client.aclose()


@app.get("/health")
async def health():
    """健康检查。"""
    return {"status": "ok"}


def main():
    """python -m api 入口。"""
    import uvicorn
    port = int(os.environ.get("STORY_STUDIO_API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
