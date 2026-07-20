"""单元测试：章节摘要 + build_context 的摘要替换与预算裁剪。

覆盖 Stage 3.4：
- save_chapter_summary / load_chapter_summary / list_chapter_summaries 基础往返
- 哨兵守卫（空串 / LLM 错误前缀不写盘）
- build_context 优先用摘要，无摘要回退首段
- build_context 预算裁剪（超 max_chars 丢最旧摘要）
- outline 截断到 8000 字
"""
from __future__ import annotations

from pathlib import Path


from agents.knowledge import KnowledgeStore


class TestSummaryStore:
    def test_save_then_load_roundtrip(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        ks.save_chapter_summary(1, "主角登场，遇见师父。")
        assert ks.load_chapter_summary(1) == "主角登场，遇见师父。"

    def test_load_missing_returns_empty(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        assert ks.load_chapter_summary(99) == ""

    def test_list_chapter_summaries_sorted(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        ks.save_chapter_summary(3, "c3")
        ks.save_chapter_summary(1, "c1")
        ks.save_chapter_summary(2, "c2")
        assert ks.list_chapter_summaries() == [1, 2, 3]

    def test_empty_summary_not_saved(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        ks.save_chapter_summary(1, "")
        assert ks.load_chapter_summary(1) == ""

    def test_sentinel_summary_not_saved(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        ks.save_chapter_summary(1, "[LLM API error: timeout]")
        assert ks.load_chapter_summary(1) == ""


class TestBuildContextUsesSummaries:
    def test_uses_summary_when_available(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        ks.save_chapter(1, "第一章的完整正文，很长很长……\n\n第二段。", "scene_writer")
        ks.save_chapter_summary(1, "这是摘要")
        ctx = ks.build_context(chapter_num=2)
        # 摘要应出现在 context 里，而不是首段
        assert "这是摘要" in ctx
        assert "Ch 1: 这是摘要" in ctx

    def test_falls_back_to_first_paragraph_without_summary(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        ks.save_chapter(1, "首段内容。\n\n第二段。", "scene_writer")
        ctx = ks.build_context(chapter_num=2)
        assert "Ch 1: 首段内容。" in ctx

    def test_excludes_current_chapter(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        ks.save_chapter(1, "第一章。", "scene_writer")
        ks.save_chapter_summary(1, "第一章摘要")
        ctx = ks.build_context(chapter_num=1)
        # 当前章不应出现在 Completed Chapters 里
        assert "Completed Chapters" not in ctx or "Ch 1:" not in ctx.split("Priority")[0]


class TestBuildContextBudgetTruncation:
    def test_drops_oldest_when_over_budget(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        # 写 5 章，每章摘要 100 字
        for i in range(1, 6):
            ks.save_chapter(i, f"ch{i} body", "scene_writer")
            ks.save_chapter_summary(i, "字" * 100)
        # max_chars=250：5*100=500 超预算，应丢最旧的几章
        ctx = ks.build_context(chapter_num=99, max_chars=250)
        # 最旧的 Ch 1 应被丢弃，最新的 Ch 5 应保留
        assert "Ch 5:" in ctx
        assert "Ch 1:" not in ctx.split("Priority")[0]

    def test_keeps_all_when_under_budget(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        for i in range(1, 4):
            ks.save_chapter(i, f"ch{i}", "scene_writer")
            ks.save_chapter_summary(i, f"摘要{i}")
        ctx = ks.build_context(chapter_num=99, max_chars=10000)
        for i in (1, 2, 3):
            assert f"Ch {i}:" in ctx


class TestOutlineTruncation:
    def test_outline_truncated_to_8000(self, tmp_path: Path):
        ks = KnowledgeStore(str(tmp_path))
        long_outline = "章" * 20000  # 2 万字
        ks.save_outline(long_outline)
        ctx = ks.build_context()
        # outline 段不应超过约 8000 字（加上 "## Outline\n" 前缀）
        outline_section = ctx.split("## Outline\n")[1].split("\n\n")[0]
        assert len(outline_section) <= 8000
