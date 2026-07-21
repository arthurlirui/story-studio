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

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# 确保项目根在 sys.path（api.py 可能被 uvicorn 直接加载）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from jobs import JobRunner, JOB_RUNNING, JOB_QUEUED

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


app = FastAPI(title="Story Studio API", version="1.0")


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

    # 延迟导入，复用 orchestrator
    from orchestrator import StoryOrchestrator
    from agents.llm_client import LLMClient
    import copy

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

    try:
        result = await orch.phase_writing(req.chapter)
        return {"chapter": req.chapter, "result": result[:1000]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

    # 延迟导入，复用 orchestrator
    from orchestrator import StoryOrchestrator
    from agents.llm_client import LLMClient
    import copy

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

    try:
        result = await orch.phase_writing_batch(req.start_chapter, req.count)
        return {
            "start_chapter": req.start_chapter,
            "count": req.count,
            "result": result[:2000],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/novels/{job_id}")
async def cancel_novel(job_id: str):
    """取消/删除一个小说任务。"""
    runner = get_runner()
    ok = await runner.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found or already finished")
    return {"job_id": job_id, "status": "cancelled"}


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
