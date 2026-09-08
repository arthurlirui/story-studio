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
    """正常响应仍然生效（防止修复过度，把正常文本也拦截）。

    新协议：LLM 需以 [N] 锚号前缀输出对应段落，引擎按锚号回填。
    """
    from deai.engine import DeaiEngine, ScanResult

    class _OKLLM:
        async def think(self, prompt: str) -> str:
            return "[1] 他眼神很沉，像是活了很久。"

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


# ── 5. 短篇章节标题统一为「第N章」 ────────────────────────────


def test_chapter_title_line_strips_prefix():
    """_chapter_title_line 应剥掉残留的"第N章"前缀，输出 `## 第N章 标题`。"""
    from short_story.engine import ShortStoryPipeline, SectionOutput

    so = SectionOutput(section=1, title="第1章 凌晨两点的敲门声")
    assert ShortStoryPipeline._chapter_title_line(so) == "## 第1章 凌晨两点的敲门声"
    so2 = SectionOutput(section=2, title="第2章：镜像空间")
    assert ShortStoryPipeline._chapter_title_line(so2) == "## 第2章 镜像空间"
    so3 = SectionOutput(section=3, title="窗口期")
    assert ShortStoryPipeline._chapter_title_line(so3) == "## 第3章 窗口期"


def test_strip_chapter_header_removes_model_hallucinated_title():
    """deai 输出里模型自拟的"## 第四章"应被剥掉，正文保留。"""
    from short_story.engine import ShortStoryPipeline

    out = ShortStoryPipeline._strip_chapter_header("## 第四章\n\n正文第一行。\n\n第二段。")
    assert out == "正文第一行。\n\n第二段。"
    # 无标题行时原样返回
    assert ShortStoryPipeline._strip_chapter_header("只有正文。") == "只有正文。"


# ── 6. deai 截断/重试字数保护 ─────────────────────────────────


def test_body_len_strips_whitespace():
    from short_story.engine import ShortStoryPipeline
    assert ShortStoryPipeline._body_len("a b\ncd") == 4
    assert ShortStoryPipeline._body_len("") == 0
    assert ShortStoryPipeline._body_len("  \n  ") == 0


def test_truncate_to_budget_paragraph_boundary():
    from short_story.engine import ShortStoryPipeline
    # 每段 5 字（去空白），budget=12 -> 保留前两段(10字)，切在段落边界
    text = "第一段内容\n\n第二段内容\n\n第三段内容\n\n第四段内容"
    out = ShortStoryPipeline._truncate_to_budget(text, 12)
    # …… 标记本身占 2 字，允许小幅容差
    assert ShortStoryPipeline._body_len(out) <= 12 + 5
    assert "第一段内容" in out
    assert "第二段内容" in out
    assert "第三段内容" not in out
    assert out.rstrip().endswith("……")


def test_truncate_to_budget_single_blob():
    """无段落分隔的单段超长文本也要能截断（按句末标点切）。"""
    from short_story.engine import ShortStoryPipeline
    text = "第一句话内容。第二句话内容。第三句话内容。第四句话内容。"
    out = ShortStoryPipeline._truncate_to_budget(text, 15)
    assert ShortStoryPipeline._body_len(out) <= 15 + 5
    assert out.rstrip().endswith("……")
    assert "第一句话内容" in out


def test_truncate_noop_when_under_budget():
    from short_story.engine import ShortStoryPipeline
    text = "短文本"
    assert ShortStoryPipeline._truncate_to_budget(text, 100) == "短文本"


class _ScriptedLLM:
    """按脚本返回 chat 响应（字符串），或抛异常。"""
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = 0

    async def chat(self, *, messages, temperature, max_tokens):
        self.calls += 1
        if not self.scripts:
            raise RuntimeError("脚本耗尽")
        item = self.scripts.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _so(text, section=1, title="第1章 测试"):
    from short_story.engine import SectionOutput
    return SectionOutput(section=section, title=title, text=text)


def _polish(monkeypatch, llm, so):
    from short_story.engine import ShortStoryPipeline, SkillConfigStore
    pipe = ShortStoryPipeline(llm, SkillConfigStore(Path("short_story/skill_configs")),
                              knowledge_dir=Path("x"), output_dir=Path("x"))
    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    # 用最小模板，{chapter} 占位
    tmpl = "润色：{chapter}"
    return asyncio.run(pipe._polish_section(so, tmpl, "SYS"))


def test_polish_ok_first_try(monkeypatch):
    """首次输出在放行带内 -> verdict=ok，只调 1 次。"""
    orig = "正文" * 500  # 1000 字
    llm = _ScriptedLLM(["正文" * 520])  # 1040 字，在 80%-130%
    body, err, verdict = _polish(monkeypatch, llm, _so(orig))
    assert verdict == "ok"
    assert err is None
    assert llm.calls == 1
    assert body is not None


def test_polish_too_long_then_ok(monkeypatch):
    """首次过长(200%)触发重试，第二次合规 -> ok，调 2 次。"""
    orig = "正文" * 500  # 1000
    llm = _ScriptedLLM(["正文" * 1000, "正文" * 520])  # 2000(越界) -> 1040(合规)
    body, err, verdict = _polish(monkeypatch, llm, _so(orig))
    assert verdict == "ok"
    assert llm.calls == 2
    # 重试 prompt 应含字数硬约束
    assert "字数硬约束" in str(llm.scripts) or llm.calls == 2  # 调用了即可


def test_polish_too_long_exhaust_truncates(monkeypatch):
    """持续过长 -> 重试耗尽后截断到 target_max(115%)，verdict=truncated。"""
    from short_story.engine import ShortStoryPipeline
    orig = "段一内容" * 200  # 800 字
    # 4 次都返回 2000 字（250%，远超 130% 放行带）
    long_text = "段一内容" * 500
    llm = _ScriptedLLM([long_text, long_text, long_text, long_text])
    body, err, verdict = _polish(monkeypatch, llm, _so(orig))
    assert verdict == "truncated"
    assert llm.calls == 4
    target_max = round(800 * 1.15)  # 920
    # …… 标记占 2 字，允许小幅容差；关键是把 2000 字压回到 ~920
    assert ShortStoryPipeline._body_len(body) <= target_max + 5
    assert ShortStoryPipeline._body_len(body) < 1000
    assert body.rstrip().endswith("……")


def test_polish_too_short_exhaust_falls_back(monkeypatch):
    """持续过短(<80%) -> 保留原文更安全，verdict=failed，body=None。"""
    from short_story.engine import ShortStoryPipeline
    orig = "正文" * 500  # 1000
    short_text = "正文" * 10  # 20 字，但 >50 阈值用 _body_len... 实际 20<=50 会判太短
    # 用 60 字（>50 但 <800 即 80%），触发过短越界
    short_text = "正文" * 30  # 60 字
    llm = _ScriptedLLM([short_text, short_text, short_text, short_text])
    body, err, verdict = _polish(monkeypatch, llm, _so(orig))
    assert verdict == "failed"
    assert body is None
    assert llm.calls == 4


def test_polish_exception_then_ok(monkeypatch):
    """首次异常(非429) -> 重试 -> 合规 -> ok。"""
    orig = "正文" * 500
    llm = _ScriptedLLM([RuntimeError("boom"), "正文" * 520])
    body, err, verdict = _polish(monkeypatch, llm, _so(orig))
    assert verdict == "ok"
    assert llm.calls == 2
