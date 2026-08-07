"""SSE 流式端点 - token 流式生成 / job 进度 / 智能体活动。

用 sse-starlette 的 EventSourceResponse 把 async generator 桥接为 SSE。
桥接现有 llm_client.generate_stream 和 worklog.read_recent。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()

# 尝试导入 sse-starlette；未装时给出友好错误而非 import 失败
try:
    from sse_starlette.sse import EventSourceResponse
    _SSE_AVAILABLE = True
except ImportError:
    _SSE_AVAILABLE = False


def _require_sse():
    if not _SSE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="SSE 端点需要 sse-starlette，请运行 pip install -e '.[api]'",
        )


@router.get("/novels/{job_id}/stream/{chapter}")
async def stream_chapter(job_id: str, chapter: int, request: Request):
    """token 流式输出某章生成过程。

    桥接 llm_client.generate_stream -> SSE。
    客户端用 EventSource 或 AI SDK useChat 消费。
    """
    _require_sse()
    from api.legacy import _build_orch_for_job, get_runner
    from agents.llm_client import LLMClient

    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def _event_generator():
        """生成 SSE 事件流。"""
        orch, client = await _build_orch_for_job(job)
        try:
            # 构造写作 prompt：用 knowledge.build_context 提供上下文
            context = orch.knowledge.build_context(chapter)
            outline = orch.knowledge.load_outline() or ""
            prompt = (
                f"请撰写第 {chapter} 章。\n\n"
                f"## 大纲内容\n{outline[:8000]}\n\n"
                f"## 上下文\n{context[:60000]}\n\n"
                f"请开始写第 {chapter} 章正文。"
            )
            # 取 scene_writer 的 system prompt 作为 system message
            sw = orch.scene_writers[0] if orch.scene_writers else None
            system = None
            if sw:
                sp = getattr(sw, "system_prompt", None)
                system = sp() if callable(sp) else sp

            yield {"event": "start", "data": json.dumps({"chapter": chapter}, ensure_ascii=False)}

            # 流式生成
            async for token in client.generate_stream(
                prompt=prompt,
                system=system,
                model=sw.model if sw else orch.cfg.main_model,
                temperature=sw.temperature if sw else 0.9,
                max_tokens=sw.max_tokens if sw else 8192,
            ):
                if await request.is_disconnected():
                    break
                yield {"event": "token", "data": token}

            yield {"event": "done", "data": json.dumps({"chapter": chapter}, ensure_ascii=False)}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)}
        finally:
            await client.aclose()

    return EventSourceResponse(_event_generator())


@router.get("/novels/{job_id}/events")
async def stream_job_events(job_id: str, request: Request):
    """job 进度事件流。

    轮询 job 状态变化（phase/progress），每次变化推一个 SSE 事件。
    客户端用 EventSource 消费，比 polling 更省带宽。
    """
    _require_sse()
    from api.legacy import get_runner

    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def _event_generator():
        """轮询 job 状态，变化时推送。"""
        last_snapshot = None
        while not await request.is_disconnected():
            job = runner.get(job_id)
            if job is None:
                yield {"event": "error", "data": json.dumps({"error": "job vanished"})}
                break
            snapshot = json.dumps(job.to_dict(), ensure_ascii=False, default=str)
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                yield {"event": "progress", "data": snapshot}
            if job.status in ("succeeded", "failed", "cancelled"):
                break
            await asyncio.sleep(1.0)

    return EventSourceResponse(_event_generator())


@router.get("/novels/{job_id}/agents/events")
async def stream_agent_events(job_id: str, request: Request):
    """智能体活动日志流。

    轮询 worklog（JSONL），新条目时推送。
    展示哪个 agent 在 think、做了什么、verdict -- 差异化功能。
    """
    _require_sse()
    from api.legacy import get_runner

    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def _event_generator():
        """轮询 worklog 新条目。"""
        from agents.worklog import WorkLog

        kd = Path(job.knowledge_dir)
        # WorkLog 接收的是 JSONL 文件路径而非知识库目录；
        # 与 orchestrator 写入侧保持一致，否则 read_recent 永远读不到条目
        worklog = WorkLog(kd / "story" / "agent_worklog.jsonl")
        seen = 0
        while not await request.is_disconnected():
            entries = worklog.read_recent(50)
            new = entries[seen:]
            for e in new:
                yield {"event": "agent", "data": json.dumps(e, ensure_ascii=False, default=str)}
            seen = len(entries)

            job = runner.get(job_id)
            if job and job.status in ("succeeded", "failed", "cancelled"):
                # 推送剩余后退出
                entries = worklog.read_recent(100)
                for e in entries[seen:]:
                    yield {"event": "agent", "data": json.dumps(e, ensure_ascii=False, default=str)}
                yield {"event": "done", "data": json.dumps({"status": job.status})}
                break
            await asyncio.sleep(2.0)

    return EventSourceResponse(_event_generator())


class StreamChatRequest(BaseModel):
    """直接与某 agent 对话的流式请求。"""

    message: str = Field(..., description="发送给 agent 的消息")
    agent: str = Field("showrunner", description="agent 角色名（如 showrunner / scene_writer）")


@router.post("/novels/{job_id}/chat")
async def chat_with_agent(job_id: str, req: StreamChatRequest, request: Request):
    """与某 job 的指定 agent 流式对话。

    POST 而非 GET（有 body），用 SSE 返回流式回复。
    """
    _require_sse()
    from api.legacy import _build_orch_for_job, get_runner

    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def _event_generator():
        orch, client = await _build_orch_for_job(job)
        try:
            agent = orch.agents.get(req.agent) or orch.agents.get(req.agent.lower())
            if agent is None:
                yield {"event": "error", "data": json.dumps(
                    {"error": f"agent {req.agent} not found, available: {list(orch.agents.keys())}"})}
                return
            sp = getattr(agent, "system_prompt", None)
            system = sp() if callable(sp) else sp
            yield {"event": "start", "data": json.dumps({"agent": req.agent})}
            async for token in client.generate_stream(
                prompt=req.message, system=system,
                model=agent.model, temperature=agent.temperature,
                max_tokens=agent.max_tokens,
            ):
                if await request.is_disconnected():
                    break
                yield {"event": "token", "data": token}
            yield {"event": "done", "data": "{}"}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
        finally:
            await client.aclose()

    return EventSourceResponse(_event_generator())
