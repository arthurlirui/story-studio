"""单元测试：KnowledgeStore 的 research 子库（变体 + 系列两层）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.knowledge import KnowledgeStore


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(str(tmp_path / "knowledge"))


@pytest.fixture
def store_with_series(tmp_path: Path) -> KnowledgeStore:
    series_research = tmp_path / "series_research"
    series_research.mkdir()
    (series_research / "hot_events.md").write_text("## 系列热点\n共享热点内容", encoding="utf-8")
    (series_research / "creation_techniques.md").write_text(
        "## 系列创作手法\n共享手法", encoding="utf-8"
    )
    return KnowledgeStore(
        base_dir=str(tmp_path / "knowledge"),
        series_research_dir=str(series_research),
    )


class TestSaveLoadResearch:
    def test_save_and_load(self, store: KnowledgeStore):
        store.save_research("hot_events", "## 热点\n内容")
        assert store.load_research("hot_events") == "## 热点\n内容"

    def test_save_empty_skipped(self, store: KnowledgeStore):
        store.save_research("empty", "")
        assert store.load_research("empty") == ""

    def test_load_missing_returns_empty(self, store: KnowledgeStore):
        assert store.load_research("nonexistent") == ""

    def test_safe_topic_sanitizes(self, store: KnowledgeStore):
        store.save_research("热点 事件/分类", "内容")
        # 读回应能成功
        assert store.load_research("热点 事件/分类") == "内容"


class TestSeriesFallback:
    def test_variant_overrides_series(self, store_with_series: KnowledgeStore):
        store_with_series.save_research("hot_events", "## 变体热点\n本作专属")
        assert "变体热点" in store_with_series.load_research("hot_events")

    def test_falls_back_to_series(self, store_with_series: KnowledgeStore):
        # 变体未写，应回退到系列层
        result = store_with_series.load_research("hot_events")
        assert "系列热点" in result

    def test_list_merges_topics(self, store_with_series: KnowledgeStore):
        store_with_series.save_research("important_events", "重要事件")
        topics = store_with_series.list_research_topics()
        assert "hot_events" in topics  # 来自系列层
        assert "creation_techniques" in topics  # 来自系列层
        assert "important_events" in topics  # 来自变体层


class TestGetAllResearch:
    def test_includes_variant_and_series(self, store_with_series: KnowledgeStore):
        store_with_series.save_research("important_events", "重要事件内容")
        text = store_with_series.get_all_research()
        assert "important_events" in text
        assert "系列热点" in text  # 系列层

    def test_variant_appears_before_series(self, store_with_series: KnowledgeStore):
        # 变体写一个 *不同* 的主题（不覆盖系列层的 hot_events），
        # 验证变体层在输出中先于系列层
        store_with_series.save_research("important_events", "## 变体层")
        text = store_with_series.get_all_research()
        variant_pos = text.find("变体层")
        series_pos = text.find("系列热点")
        # 变体层先于系列层出现
        assert 0 <= variant_pos < series_pos

    def test_truncates_per_doc(self, store: KnowledgeStore):
        long_content = "X" * 5000
        store.save_research("big", long_content)
        text = store.get_all_research(max_per_doc=100, total_budget=10000)
        # 单篇被截断到 100 字
        assert text.count("X") <= 100

    def test_total_budget(self, store: KnowledgeStore):
        for i in range(5):
            store.save_research(f"topic_{i}", "Y" * 1000)
        text = store.get_all_research(max_per_doc=2000, total_budget=1500)
        # 总和受预算限制
        assert text.count("Y") <= 1500


class TestBuildContextInjection:
    def test_research_in_build_context(self, store: KnowledgeStore):
        store.save_research("hot_events", "## 调研发现\n重要热点内容")
        ctx = store.build_context()
        assert "调研知识库" in ctx
        assert "重要热点内容" in ctx

    def test_no_research_no_section(self, store: KnowledgeStore):
        ctx = store.build_context()
        # 无调研时不该出现调研 section
        assert "调研知识库" not in ctx
