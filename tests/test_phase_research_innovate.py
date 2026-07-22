"""集成测试：orchestrator.phase_research / phase_innovate 端到端流程。

用 FakeLLMClient + FakeWebSearch 模拟 LLM 与搜索 provider，验证：
- C2: phase_research 累加所有 topic 的 token usage（不是只记最后一个）
- C3: phase_innovate 排除 highlights slug（不自注入）
- C4: phase_research 尊重 cfg.research_max_topics
- M5: phase_innovate 收到完整 brief 而非 project_name
- M8: LLM 失败时不污染 KB（不写错误占位符到 research/）

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 手动驱动 async 用例。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.web_search import SearchResult
from config import StudioConfig
from orchestrator import StoryOrchestrator


def _run(coro):
    """新建 event loop 跑完协程，替代 pytest-asyncio。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fakes ────────────────────────────────────────────────────


class FakeLLMClient:
    """模拟 LLM，按调用次数递增 usage，便于验证 C2 累加。"""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["LLM 报告"]
        self._idx = 0
        self.last_usage: dict | None = None
        self.calls: list[str] = []
        self.usage_seq = [
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            {"prompt_tokens": 200, "completion_tokens": 60, "total_tokens": 260},
            {"prompt_tokens": 300, "completion_tokens": 70, "total_tokens": 370},
            {"prompt_tokens": 400, "completion_tokens": 80, "total_tokens": 480},
            {"prompt_tokens": 500, "completion_tokens": 90, "total_tokens": 590},
        ]

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        prompt = messages[-1]["content"] if messages else ""
        self.calls.append(prompt)
        resp = self.responses[self._idx % len(self.responses)]
        self._idx += 1
        # 每次调用累加 usage，让 agent.last_usage 每次不同
        self.last_usage = self.usage_seq[(self._idx - 1) % len(self.usage_seq)]
        return resp


class FailingLLMClient:
    """模拟 LLM，chat 总是抛异常，验证 M8 不污染 KB。"""

    def __init__(self):
        self.last_usage: dict | None = None

    async def chat(self, **kwargs) -> str:
        raise RuntimeError("LLM down")


class FakeWebSearch:
    """模拟 WebSearchProvider，返回固定结果。"""

    name = "fake"

    def __init__(self, results: list[SearchResult] | None = None):
        self.results = results or [
            SearchResult(title="t1", snippet="s1", url="http://a", source="fake")
        ]
        self.queries: list[str] = []

    async def search(self, query: str, count: int = 5):
        self.queries.append(query)
        return self.results[:count]

    async def aclose(self):
        pass


# ── Fixtures ────────────────────────────────────────────────


def _make_orch(tmp_path, client, web_search=None, max_topics=4):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
    )
    # C4: research_max_topics 可注入
    cfg.research_max_topics = max_topics
    orch = StoryOrchestrator(cfg, client=client)
    orch.project_name = "测试小说"
    # 跳过限流睡眠
    async def _no_pause():
        return None
    orch._rate_limit_pause = _no_pause
    # 注入 fake web search
    if web_search is not None:
        orch.web_search = web_search
    return orch


# ── Tests ────────────────────────────────────────────────────


def test_phase_research_writes_4_docs(tmp_path):
    """phase_research 应为每个 topic 写一篇 research/{slug}.md。"""
    client = FakeLLMClient(responses=["## 热点报告\n内容A"])
    ws = FakeWebSearch()
    orch = _make_orch(tmp_path, client, web_search=ws)

    _run(orch.phase_research("一个关于剑客的故事"))

    research_dir = Path(orch.cfg.knowledge_dir) / "research"
    slugs = {f.stem for f in research_dir.glob("*.md")}
    # 4 个 topic slug 都应落盘
    assert {"hot_events", "important_events", "similar_novels", "creation_techniques"} <= slugs


def test_phase_research_records_usage_all_topics(tmp_path):
    """C2 修复：phase_research 应累加所有 topic 的 usage，不是只记最后一个。

    FakeLLMClient 每次返回递增的 usage；4 次 think() 累加 total_tokens 应为
    150+260+370+480 = 1260，而非最后一次 480。
    """
    client = FakeLLMClient()
    ws = FakeWebSearch()
    orch = _make_orch(tmp_path, client, web_search=ws)

    _run(orch.phase_research("剑客故事"))

    # 找 light_model 的 bucket（topic_researcher 用 light tier）
    light_model = orch.topic_researcher.model
    bucket = orch.run_cost.get(light_model)
    assert bucket is not None, f"light_model bucket 未记录: {orch.run_cost}"
    # 4 次调用累加（150+260+370+480=1260），若只记最后一次则是 480
    assert bucket["total_tokens"] == 1260, (
        f"C2 回归：usage 未累加，total_tokens={bucket['total_tokens']} (期望 1260)"
    )
    assert bucket["calls"] == 4


def test_phase_research_llm_failure_no_pollution(tmp_path):
    """M8 修复：LLM 失败时不写错误占位符到 research/ 目录。"""
    client = FailingLLMClient()
    ws = FakeWebSearch()
    orch = _make_orch(tmp_path, client, web_search=ws)

    _run(orch.phase_research("剑客故事"))

    research_dir = Path(orch.cfg.knowledge_dir) / "research"
    # 失败占位符不应落盘
    for f in research_dir.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        assert "调研综合失败" not in content, (
            f"M8 回归：{f.name} 含错误占位符"
        )


def test_phase_innovate_excludes_highlights_from_research(tmp_path):
    """C3 修复：phase_innovate 读取 get_all_research 不应包含 highlights slug。

    预置 highlights.md 到 research/，innovate 调用时 prompt 中不应出现 highlights 内容。
    """
    # 先写一份 highlights.md（模拟上一轮 Innovator 的产物）
    knowledge_dir = tmp_path / "knowledge" / "research"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "highlights.md").write_text(
        "## 创新亮点清单\n\n- 这是一个不应被自注入的 HIGHLIGHTS_MARKER",
        encoding="utf-8",
    )
    # 再写一个正常 research 文档
    (knowledge_dir / "hot_events.md").write_text(
        "## 热点报告\n\n- HOT_EVENTS_MARKER",
        encoding="utf-8",
    )

    client = FakeLLMClient(responses=["## 创新亮点\n\n亮点1"])
    orch = _make_orch(tmp_path, client)

    _run(orch.phase_innovate("剑客故事"))

    # Innovator 的 prompt 不应包含 highlights 自注入标记
    last_prompt = client.calls[-1]
    assert "HIGHLIGHTS_MARKER" not in last_prompt, (
        f"C3 回归：innovate prompt 含 highlights 内容: {last_prompt[:200]}"
    )
    # 正常的 hot_events 应被注入
    assert "HOT_EVENTS_MARKER" in last_prompt


def test_phase_innovate_brief_passed(tmp_path):
    """M5 修复：phase_innovate 应收到完整 brief，不只是 project_name。"""
    client = FakeLLMClient(responses=["## 创新亮点\n\n亮点1"])
    orch = _make_orch(tmp_path, client)

    long_brief = "一个关于古代剑客在乱世中寻找自我的长篇故事，融合悬疑与武侠元素"
    _run(orch.phase_innovate(long_brief))

    last_prompt = client.calls[-1]
    assert long_brief in last_prompt, (
        f"M5 回归：brief 未透传，prompt: {last_prompt[:200]}"
    )
    # project_name 只是短书名，不应替代完整 brief
    assert "测试小说" not in long_brief


def test_phase_research_respects_max_topics(tmp_path):
    """C4 修复：research_max_topics=2 时只调研前 2 个 topic。"""
    client = FakeLLMClient(responses=["报告"])
    ws = FakeWebSearch()
    orch = _make_orch(tmp_path, client, web_search=ws, max_topics=2)

    _run(orch.phase_research("剑客故事"))

    # 只应搜索 2 次（2 个 topic 各 1 次）
    assert len(ws.queries) == 2, (
        f"C4 回归：max_topics=2 但搜索了 {len(ws.queries)} 次"
    )
    # 只应写 2 个 research 文档
    research_dir = Path(orch.cfg.knowledge_dir) / "research"
    slugs = {f.stem for f in research_dir.glob("*.md")}
    assert slugs == {"hot_events", "important_events"}, (
        f"C4 回归：应只写前 2 个 topic，实际: {slugs}"
    )
