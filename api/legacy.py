"""原 api.py 的 novels/tasks CRUD 端点（迁移为 APIRouter）。

端点：
- POST   /novels            提交新小说 job
- GET    /novels            列出所有 job
- GET    /novels/{id}       查看单个 job 状态
- GET    /novels/{id}/chapters/{n}  读取某章节正文
- POST   /novels/{id}/revise  触发某 job 重写指定章节
- POST   /novels/{id}/batch  批次并行写作
- DELETE /novels/{id}       取消/删除 job
- GET    /novels/{id}/tasks  任务清单
- POST   /novels/{id}/tasks/{n}/run  执行单任务
- POST   /novels/{id}/run-all  执行所有任务
- POST   /novels/{id}/resume  断点恢复

鉴权中间件与 CORS 已在 api/__init__.py 的 create_app() 中统一注册。
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from jobs import (
    JOB_RUNNING,
    JOB_QUEUED,
    JOB_SUCCEEDED,
    JOB_FAILED,
    JOB_RECOVERABLE,
    make_on_progress,
    finalize_job_after_run_all,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_runner():
    """从包级 get_runner 复用（避免每端点重建 JobRunner）。"""
    from api import get_runner as _gr
    return _gr()


async def _build_orch_for_job(job):
    """为指定 job 构造独立的 StoryOrchestrator + LLMClient。

    调用方必须在 finally 中 await client.aclose() 释放连接池，
    否则会泄漏 httpx.AsyncClient。返回 (orch, client)。
    """
    from orchestrator import StoryOrchestrator
    from agents.llm_client import LLMClient

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


# ── 请求/响应模型 ────────────────────────────────────────────


class NovelCreate(BaseModel):
    brief: str = Field(..., description="创作需求/企划描述")
    project_name: str = Field("", description="项目名（书名）")
    total_chapters: int | None = Field(None, description="目标章节数", ge=1, le=200)
    write_mode: str = Field("sequential", description="写作模式：sequential / batch")


class NovelRevise(BaseModel):
    chapter: int = Field(..., description="要重写的章节号", ge=1)


class BatchWrite(BaseModel):
    start_chapter: int = Field(..., description="起始章节号", ge=1)
    count: int = Field(..., description="本批次章节数", ge=1, le=20)


# ── 端点 ──────────────────────────────────────────────────────


@router.post("/novels")
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


@router.get("/novels")
async def list_novels():
    """列出所有小说任务。"""
    runner = get_runner()
    return {"novels": [j.to_dict() for j in runner.list()]}


@router.get("/novels/{job_id}")
async def get_novel(job_id: str):
    """查看单个小说任务状态。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@router.get("/novels/{job_id}/chapters/{chapter_num}")
async def get_chapter(job_id: str, chapter_num: int):
    """读取某章节正文。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    chapter_path = Path(job.knowledge_dir) / "story" / "chapters" / f"chapter_{chapter_num:03d}.md"
    if not chapter_path.exists():
        raise HTTPException(status_code=404, detail=f"chapter {chapter_num} not found")
    return {"chapter": chapter_num, "content": chapter_path.read_text(encoding="utf-8")}


@router.post("/novels/{job_id}/revise")
async def revise_chapter(job_id: str, req: NovelRevise):
    """触发某 job 重写指定章节（仅当 job 已完成或运行中）。"""
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


@router.post("/novels/{job_id}/batch")
async def batch_write(job_id: str, req: BatchWrite):
    """触发某 job 的批次并行写作（预协调简报 -> 并行写作 -> 融合门）。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == JOB_RUNNING or job.status == JOB_QUEUED:
        raise HTTPException(status_code=409, detail="job still running, cannot batch write")

    orch, client = await _build_orch_for_job(job)
    try:
        result = await orch.phase_writing_batch(req.start_chapter, req.count)
        return {"start_chapter": req.start_chapter, "count": req.count, "result": result[:2000]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.aclose()


@router.delete("/novels/{job_id}")
async def cancel_novel(job_id: str):
    """取消/删除一个小说任务。"""
    runner = get_runner()
    ok = await runner.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found or already finished")
    return {"job_id": job_id, "status": "cancelled"}


# ── 任务清单端点（TaskPlanner）─────────────────────────────────


async def _build_planner_for_job(job_id: str):
    """为指定 job 构造 TaskPlanner。返回 (planner, orch, job, client)。"""
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


@router.get("/novels/{job_id}/tasks")
async def get_tasks(job_id: str):
    """返回该 job 的任务清单。"""
    planner, _orch, job, client = await _build_planner_for_job(job_id)
    try:
        plan = planner.load_plan()
        if plan is None:
            return {"job_id": job_id, "plan": None, "message": "尚未生成任务清单"}
        return {"job_id": job_id, "plan": plan.to_dict(), "summary": planner.summary()}
    finally:
        await client.aclose()


@router.post("/novels/{job_id}/tasks/{task_n}/run")
async def run_task(job_id: str, task_n: int):
    """执行该 job 的第 N 个任务（1-based）。"""
    planner, _orch, job, client = await _build_planner_for_job(job_id)
    runner = get_runner()
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


@router.post("/novels/{job_id}/run-all")
async def run_all_tasks(job_id: str):
    """按序执行该 job 的所有未完成任务。"""
    planner, orch, job, client = await _build_planner_for_job(job_id)
    runner = get_runner()
    async with runner._get_job_lock(job_id):
        try:
            if job.status == JOB_RUNNING or job.status == JOB_QUEUED:
                raise HTTPException(status_code=409, detail="job still running")
            if planner.load_plan() is None:
                raise HTTPException(status_code=404, detail="task plan not found")
            job.status = JOB_RUNNING
            job.touch()
            runner._save_index()
            _on_progress = make_on_progress(job, planner, orch, on_save=runner._save_index)
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
                failed_tasks = [f"#{t.id}({t.phase})" for t in planner.plan.tasks if t.status == "failed"]
                job.error = f"任务失败 {s['failed']} 个：{', '.join(failed_tasks)}"
                job.touch()
                runner._save_index()
                return {
                    "job_id": job_id, "status": "partial_failure", "summary": s,
                    "failed_tasks": [{"id": t.id, "phase": t.phase, "error": t.error}
                                     for t in planner.plan.tasks if t.status == "failed"],
                }
            finalize_job_after_run_all(job, planner, orch, fallback_total=0)
            runner._save_index()
            return {"job_id": job_id, "status": "succeeded", "summary": s}
        finally:
            await client.aclose()


@router.post("/novels/{job_id}/resume")
async def resume_novel(job_id: str):
    """手动恢复一个 failed/recoverable 的 job，从已有 task_plan.json 断点续跑。"""
    planner, orch, job, client = await _build_planner_for_job(job_id)
    runner = get_runner()
    async with runner._get_job_lock(job_id):
        try:
            if job.status not in (JOB_FAILED, JOB_RECOVERABLE, JOB_SUCCEEDED):
                raise HTTPException(
                    status_code=409,
                    detail=f"job status {job.status} cannot resume (only failed/recoverable/succeeded)",
                )
            existing = planner.load_plan()
            if existing is None:
                raise HTTPException(status_code=404, detail="no task_plan.json to resume from, POST /novels first")
            job.status = JOB_RUNNING
            job.error = None
            job.touch()
            runner._save_index()
            _on_progress = make_on_progress(job, planner, orch, on_save=runner._save_index)
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
                failed_tasks = [f"#{t.id}({t.phase})" for t in planner.plan.tasks if t.status == "failed"]
                job.error = f"恢复后任务失败 {s['failed']} 个：{', '.join(failed_tasks)}"
                job.touch()
                runner._save_index()
                return {
                    "job_id": job_id, "status": "partial_failure", "summary": s,
                    "failed_tasks": [{"id": t.id, "phase": t.phase, "error": t.error}
                                     for t in planner.plan.tasks if t.status == "failed"],
                }
            finalize_job_after_run_all(job, planner, orch, fallback_total=0)
            runner._save_index()
            return {"job_id": job_id, "status": "succeeded", "summary": s}
        finally:
            await client.aclose()
