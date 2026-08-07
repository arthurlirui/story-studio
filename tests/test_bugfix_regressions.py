"""回归测试：审阅发现的 4 个 bug 的修复验证。

1. api/stream.py agent-events: WorkLog 应指向 story/agent_worklog.jsonl（此前传目录）
2. deai/engine.py: LLM 重写应识别真实错误哨兵 "[LLM API error"（此前查 "ERROR"）
3. jobs.py: JobRunner 无运行中事件循环时构造不应崩，恢复任务延迟启动
4. agents/llm_client.py: TransportError 应短退避重试（此前直接判死）

不触达真实网络：httpx / LLM client 全部 mock。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agents.llm_client import LLMClient, LLM_ERROR_PREFIX, _ERROR_SENTINEL


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── 1. api/stream.py WorkLog 路径 ─────────────────────────────


def test_stream_agent_events_worklog_path():
    """agent-events 端点用的 WorkLog 应指向与 orchestrator 写入侧相同的文件。"""
    src = Path("api/stream.py").read_text(encoding="utf-8")
    assert 'WorkLog(kd / "story" / "agent_worklog.jsonl")' in src
    assert "WorkLog(kd)" not in src


# ── 2. deai/engine.py 错误哨兵 ─────────────────────────────────


class _SentinelLLM:
    """模拟 LLM 客户端：think 总返回错误哨兵。"""

    async def think(self, prompt: str) -> str:
        return _ERROR_SENTINEL.format("boom")


def test_deai_rewrite_llm_rejects_error_sentinel():
    """LLM 返回错误哨兵时，正文必须原样返回（此前哨兵会被当重写结果混进正文）。"""
    from deai.engine import DeaiEngine, ScanResult

    engine = DeaiEngine(llm_client=_SentinelLLM())
    text = "他的眼神无比深邃，仿佛承载着千年的沧桑。"
    scan = [ScanResult(rule_id=1, rule_name="ai_tone", category="style",
                       severity=1, match_count=1, samples=[text])]
    out, calls = _run(engine.rewrite_llm(text, scan))
    assert out == text, "错误哨兵响应不应修改正文"
    assert calls == 0


def test_deai_rewrite_llm_applies_real_response():
    """正常响应仍然生效（防止修复过度，把正常文本也拦截）。"""
    from deai.engine import DeaiEngine, ScanResult

    class _OKLLM:
        async def think(self, prompt: str) -> str:
            return "他眼神很沉，像是活了很久。"

    engine = DeaiEngine(llm_client=_OKLLM())
    sample = "他的眼神无比深邃，仿佛承载着千年的沧桑与重担。"
    text = f"开篇。{sample}结尾。"
    scan = [ScanResult(rule_id=1, rule_name="ai_tone", category="style",
                       severity=1, match_count=1, samples=[sample])]
    out, calls = _run(engine.rewrite_llm(text, scan))
    assert calls == 1
    assert "他眼神很沉" in out
    assert sample not in out


# ── 3. jobs.py 无事件循环构造 ──────────────────────────────────


def test_jobrunner_constructs_without_running_loop(tmp_path: Path):
    """同步上下文（CLI/脚本/测试）直接 new JobRunner 不应抛 no running event loop。"""
    from config import StudioConfig
    from jobs import JobRunner, JOB_RECOVERABLE
    from planner import TaskPlan, Task
    from orchestrator_state import PHASE_WRITING

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True)
    jid = "99999_syncctx"
    kd = jobs_dir / jid / "knowledge"
    kd.mkdir(parents=True)
    TaskPlan(job_id=jid, brief="x", total_chapters=1,
             tasks=[Task(id=1, name="写作", phase=PHASE_WRITING)]).save(kd / "task_plan.json")
    (jobs_dir / "index.json").write_text(json.dumps({
        "jobs": [{
            "id": jid, "brief": "x", "status": "running", "phase": "writing",
            "progress": [0, 1], "task_progress": None,
            "created_at": 1.0, "updated_at": 2.0,
            "knowledge_dir": str(kd), "output_dir": str(jobs_dir / jid / "output"),
            "project_name": "x", "write_mode": "sequential",
            "result": None, "error": None,
        }],
        "updated_at": 2.0,
    }), encoding="utf-8")

    cfg = StudioConfig(backend="llm", llm_api_key="fake",
                       knowledge_dir=str(tmp_path / "k"),
                       output_dir=str(tmp_path / "o"))
    # 关键断言：同步构造不抛异常
    runner = JobRunner(base_dir=str(jobs_dir), cfg=cfg)
    job = runner.get(jid)
    assert job.status == "queued"
    assert jid in runner._pending_recover

    # 进入事件循环后，start_pending_recoveries 应能补启动
    async def _go():
        recovered: list[str] = []

        async def _fake_run(self, job, total_chapters):
            recovered.append(job.id)
            job.status = "succeeded"

        import jobs as jobs_mod
        orig = JobRunner._run_job
        JobRunner._run_job = _fake_run
        try:
            runner.start_pending_recoveries()
            for _ in range(100):
                await asyncio.sleep(0.02)
                if runner.get(jid).status == "succeeded":
                    break
        finally:
            JobRunner._run_job = orig
        return recovered

    recovered = _run(_go())
    assert recovered == [jid]
    assert runner._pending_recover == []


# ── 4. llm_client TransportError 重试 ──────────────────────────


from tests.test_llm_client import MockAsyncClient, _ok_response, _make_client_with_mock  # noqa: E402


class TestTransportRetry:
    def test_connect_error_retried_then_succeeds(self, monkeypatch):
        """连接重置等 TransportError 应短退避重试而非直接判死。"""
        responses = [
            httpx.ConnectError("connection reset"),
            _ok_response("recovered"),
        ]
        client, mock = _make_client_with_mock(monkeypatch, responses)
        # 加速：把退避改成 0
        monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

        result = asyncio.run(client.chat(
            messages=[{"role": "user", "content": "hi"}], max_tokens=64,
        ))
        assert result == "recovered"
        assert len(mock.calls) == 2

    def test_persistent_transport_error_returns_sentinel(self, monkeypatch):
        """持续 TransportError 最终返回错误哨兵（不抛异常）。"""
        responses = [httpx.ConnectError("down")] * 8
        client, mock = _make_client_with_mock(monkeypatch, responses)
        monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

        result = asyncio.run(client.chat(
            messages=[{"role": "user", "content": "hi"}], max_tokens=64,
        ))
        assert result.startswith(LLM_ERROR_PREFIX)
        # 重试次数不超过 MAX_RETRIES
        assert len(mock.calls) <= 8

    def test_http_5xx_still_fails_fast(self, monkeypatch):
        """5xx（如 503 无可用渠道）仍立即终止，不燃烧退避链。"""
        from tests.test_llm_client import MockResponse

        responses = [MockResponse(503, {"error": "no channel"})]
        client, mock = _make_client_with_mock(monkeypatch, responses)
        monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

        result = asyncio.run(client.chat(
            messages=[{"role": "user", "content": "hi"}], max_tokens=64,
        ))
        assert result.startswith(LLM_ERROR_PREFIX)
        assert len(mock.calls) == 1, "HTTPStatusError 不应重试"


async def _instant_sleep(*args, **kwargs):
    return None


# ── 4b. 流式侧的 yielded_any 语义 ──────────────────────────────


class _StreamMockClient:
    """模拟流式 client.stream。scripts: 每次调用弹出一个行为。

    behavior: ("error", exc)          -> 进入 stream 就抛
              ("lines", [line...])    -> 逐行 yield
    """

    def __init__(self, scripts: list):
        self.scripts = list(scripts)
        self.calls = 0
        self.is_closed = False

    def stream(self, method, url, json=None, headers=None):
        self.calls += 1
        behavior = self.scripts.pop(0)
        return _StreamCtx(behavior)

    async def aclose(self):
        self.is_closed = True


class _StreamResp:
    def __init__(self, lines):
        self.status_code = 200
        self._lines = lines

    def raise_for_status(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln


class _StreamCtx:
    def __init__(self, behavior):
        self.behavior = behavior

    async def __aenter__(self):
        kind, payload = self.behavior
        if kind == "error":
            raise payload
        return _StreamResp(payload)

    async def __aexit__(self, *a):
        return False


def _sse_line(content: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": content}}]})


class TestStreamTransportRetry:
    def test_error_before_first_token_retries(self, monkeypatch):
        """首 token 前的传输错误可安全重试。"""
        scripts = [
            ("error", httpx.ConnectError("reset")),
            ("lines", [_sse_line("你好"), "data: [DONE]"]),
        ]
        client = LLMClient("http://mock/v1", "k", "m")
        mock = _StreamMockClient(scripts)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: mock)
        monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

        async def _collect():
            return [t async for t in client.generate_stream("hi", max_tokens=64)]

        tokens = asyncio.run(_collect())
        assert tokens == ["你好"]
        assert mock.calls == 2

    def test_partial_output_then_error_aborts(self, monkeypatch):
        """已产出 token 后流中断：不得整体重试（避免正文重复）。"""
        class _DyingStream(_StreamMockClient):
            def stream(self, method, url, json=None, headers=None):
                self.calls += 1
                return _DyingCtx()

        class _DyingResp(_StreamResp):
            async def aiter_lines(self):
                yield _sse_line("部分")
                raise httpx.ReadError("mid-stream reset")

        class _DyingCtx:
            async def __aenter__(self):
                return _DyingResp([])

            async def __aexit__(self, *a):
                return False

        client = LLMClient("http://mock/v1", "k", "m")
        mock = _DyingStream([])
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: mock)
        monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

        async def _collect():
            return [t async for t in client.generate_stream("hi", max_tokens=64)]

        tokens = asyncio.run(_collect())
        # 只产出一次 "部分"，最后跟错误哨兵；绝不能重试导致 ["部分", "部分", ...]
        assert tokens[0] == "部分"
        assert tokens[-1].startswith(LLM_ERROR_PREFIX)
        assert len([t for t in tokens if t == "部分"]) == 1
        assert mock.calls == 1
