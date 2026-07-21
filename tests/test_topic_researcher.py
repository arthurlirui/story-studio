"""单元测试：agents/topic_researcher.py 与 agents/innovator.py。

用 mock client + mock WebSearchProvider 验证：
- TopicResearcher.research 把搜索结果综合成报告并写入 knowledge.save_research
- Innovator.innovate 读 knowledge.get_all_research 并产出 highlights，写入 knowledge
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.innovator import Innovator
from agents.knowledge import KnowledgeStore
from agents.topic_researcher import DEFAULT_TOPICS, TopicResearcher
from agents.web_search import MockSearchProvider, SearchResult


class FakeClient:
    """模拟 LLM client，实现 chat 接口。"""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["LLM 综合报告"]
        self._idx = 0
        self.last_usage = None

    async def chat(self, **kwargs) -> str:
        resp = self.responses[self._idx % len(self.responses)]
        self._idx += 1
        return resp


class FakeWebSearch:
    """模拟 WebSearchProvider，返回固定结果。"""

    def __init__(self, results: list[SearchResult] | None = None):
        self.results = results or []
        self.calls: list[str] = []

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        self.calls.append(query)
        return self.results


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(str(tmp_path / "knowledge"))


# ── TopicResearcher ──────────────────────────────────────────

class TestTopicResearcher:
    @pytest.mark.asyncio
    async def test_research_writes_to_kb(self, store: KnowledgeStore):
        client = FakeClient(responses=["热点报告 v1", "重要事件报告", "同类小说报告", "创作手法报告"])
        researcher = TopicResearcher(
            "热点研究员", "Topic Researcher", "调研",
            client, model="test-model", temperature=0.5,
        )
        web_search = FakeWebSearch(results=[
            SearchResult(title="t1", snippet="s1", url="http://a", source="test"),
        ])

        results = await researcher.research(
            brief="一个关于剑客的故事",
            web_search=web_search,
            knowledge=store,
        )

        # 4 个主题都应被调研
        assert len(results) == 4
        assert set(results.keys()) == {t[0] for t in DEFAULT_TOPICS}
        # 每个主题都应写入 KB
        topics_on_disk = store.list_research_topics()
        for slug, _, _ in DEFAULT_TOPICS:
            assert slug in topics_on_disk
            assert store.load_research(slug) != ""
        # 每个主题都应执行了一次搜索
        assert len(web_search.calls) == 4
        # sources 元数据应记录
        for meta in results.values():
            assert "sources" in meta
            assert len(meta["sources"]) == 1

    @pytest.mark.asyncio
    async def test_research_empty_search_still_writes_report(self, store: KnowledgeStore):
        client = FakeClient(responses=["基于内置知识的报告"] * 4)
        researcher = TopicResearcher(
            "热点研究员", "Topic Researcher", "调研",
            client, model="test-model",
        )
        web_search = FakeWebSearch(results=[])  # 搜索为空

        results = await researcher.research(
            brief="故事 brief",
            web_search=web_search,
            knowledge=store,
        )

        # 即使搜索为空，报告也应写入
        for slug in [t[0] for t in DEFAULT_TOPICS]:
            assert store.load_research(slug) != ""
        # sources 应为空列表
        for meta in results.values():
            assert meta["sources"] == []

    @pytest.mark.asyncio
    async def test_research_custom_topics(self, store: KnowledgeStore):
        client = FakeClient(responses=["报告"] * 2)
        researcher = TopicResearcher(
            "热点研究员", "Topic Researcher", "调研",
            client, model="test-model",
        )
        web_search = FakeWebSearch(results=[])

        custom_topics = [
            ("custom_a", "自定义A", "描述A"),
            ("custom_b", "自定义B", "描述B"),
        ]
        results = await researcher.research(
            brief="brief", web_search=web_search,
            knowledge=store, topics=custom_topics,
        )

        assert set(results.keys()) == {"custom_a", "custom_b"}
        assert "custom_a" in store.list_research_topics()


# ── Innovator ────────────────────────────────────────────────

class TestInnovator:
    @pytest.mark.asyncio
    async def test_innovate_writes_highlights(self, store: KnowledgeStore):
        # 预置调研文档
        store.save_research("hot_events", "## 热点\n内容")
        store.save_research("similar_novels", "## 同类小说\n内容")

        client = FakeClient(responses=["## 创新亮点清单\n\n### 亮点 1：xxx"])
        innovator = Innovator(
            "创新亮点策划师", "Innovator", "创新",
            client, model="test-model",
        )

        result = await innovator.innovate(store, brief="剑客故事")

        assert "创新亮点" in result
        # 应写入 research/highlights.md
        assert store.load_research("highlights") == result
        assert "highlights" in store.list_research_topics()

    @pytest.mark.asyncio
    async def test_innovate_empty_kb_still_runs(self, store: KnowledgeStore):
        client = FakeClient(responses=["基于 brief 的方向性建议"])
        innovator = Innovator(
            "创新亮点策划师", "Innovator", "创新",
            client, model="test-model",
        )

        # KB 为空，但应正常执行
        result = await innovator.innovate(store, brief="故事")
        assert result != ""
        assert store.load_research("highlights") == result

    @pytest.mark.asyncio
    async def test_innovate_llm_failure_writes_error_placeholder(self, store: KnowledgeStore):
        store.save_research("hot_events", "内容")

        failing_client = MagicMock()
        failing_client.chat = AsyncMock(side_effect=RuntimeError("LLM 挂了"))
        innovator = Innovator(
            "创新亮点策划师", "Innovator", "创新",
            failing_client, model="test-model",
        )

        # 不应抛异常，应返回错误占位符
        result = await innovator.innovate(store, brief="故事")
        assert "失败" in result
        assert store.load_research("highlights") == result
