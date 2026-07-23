"""单元测试：agents/knowledge.py 的 KnowledgeStore。

覆盖 Stage 1 可靠性改动：
- save_chapter 原子写（崩溃不留半截文件）
- save_continuity_log 哨兵守卫（API 错误不污染日志）
- build_context 基础结构
- save_world / save_outline / save_character 原子写
"""
from __future__ import annotations

from pathlib import Path


import pytest

from agents.knowledge import KnowledgeStore, _atomic_write_text, _LLM_ERROR_PREFIX


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(str(tmp_path / "knowledge"))


# ── _atomic_write_text ──────────────────────────────────────

class TestAtomicWrite:
    def test_writes_content_correctly(self, tmp_path: Path):
        target = tmp_path / "out" / "file.md"
        _atomic_write_text(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_no_tmp_file_left(self, tmp_path: Path):
        target = tmp_path / "file.md"
        _atomic_write_text(target, "content")
        assert not (tmp_path / "file.md.tmp").exists()
        # 列出 tmp 文件，应只有目标
        assert list(tmp_path.glob("*.md")) == [target]

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "file.md"
        _atomic_write_text(target, "v1")
        _atomic_write_text(target, "v2")
        assert target.read_text(encoding="utf-8") == "v2"


# ── save_chapter 原子写 ─────────────────────────────────────

class TestSaveChapterAtomic:
    def test_chapter_written(self, store: KnowledgeStore):
        store.save_chapter(3, "第3章内容", "scene_writer")
        assert store.load_chapter(3) == "第3章内容"

    def test_no_tmp_residue(self, store: KnowledgeStore):
        store.save_chapter(1, "内容", "editor")
        # chapters_dir 下不应有 .tmp 残留
        tmps = list(store.chapters_dir.glob("*.tmp"))
        assert tmps == []

    def test_revision_snapshot_saved(self, store: KnowledgeStore):
        store.save_chapter(2, "v1", "scene_writer")
        rev_dir = store.revisions_dir / "chapter_002"
        revs = list(rev_dir.glob("*_scene_writer.md"))
        assert len(revs) == 1
        assert revs[0].read_text(encoding="utf-8") == "v1"

    def test_revision_snapshot_no_tmp(self, store: KnowledgeStore):
        store.save_chapter(1, "x", "scene_writer")
        rev_dir = store.revisions_dir / "chapter_001"
        tmps = list(rev_dir.glob("*.tmp"))
        assert tmps == []


# ── save_continuity_log 哨兵守卫 ────────────────────────────

class TestContinuityLogGuard:
    def test_normal_content_written(self, store: KnowledgeStore):
        store.save_continuity_log("角色A在第3章受伤，第5章痊愈。")
        assert store.load_continuity_log() == "角色A在第3章受伤，第5章痊愈。"

    def test_error_sentinel_not_written(self, store: KnowledgeStore):
        sentinel = "[LLM API error: Connection refused]"
        store.save_continuity_log(sentinel)
        # 关键：不应写盘
        assert store.load_continuity_log() == ""

    def test_empty_content_not_written(self, store: KnowledgeStore):
        store.save_continuity_log("")
        assert store.load_continuity_log() == ""

    def test_existing_log_not_overwritten_by_sentinel(self, store: KnowledgeStore):
        store.save_continuity_log("已存在的连续性记录。")
        store.save_continuity_log("[LLM API error: timeout]")
        # 哨兵不应覆盖既有日志
        assert store.load_continuity_log() == "已存在的连续性记录。"

    def test_sentinel_prefix_constant_matches_client(self):
        # 与 agents/llm_client._ERROR_SENTINEL 前缀一致
        assert _LLM_ERROR_PREFIX == "[LLM API error"


# ── build_context 基础 ──────────────────────────────────────

class TestBuildContext:
    def test_empty_store_minimal_context(self, store: KnowledgeStore):
        ctx = store.build_context()
        # 空库仍含 Priority 提示
        assert "Priority" in ctx
        assert "Variant knowledge > Series knowledge" in ctx

    def test_includes_world_and_outline(self, store: KnowledgeStore):
        store.save_world("settings", "世界设定内容")
        store.save_outline("大纲内容")
        ctx = store.build_context()
        assert "世界设定内容" in ctx
        assert "大纲内容" in ctx

    def test_excludes_current_chapter(self, store: KnowledgeStore):
        store.save_chapter(1, "第一章正文段落", "scene_writer")
        store.save_chapter(2, "第二章正文段落", "scene_writer")
        ctx = store.build_context(chapter_num=2)
        assert "第一章" in ctx  # chapter 1 应在
        assert "第二章正文段落" not in ctx  # 当前章应被排除

    def test_continuity_log_in_context(self, store: KnowledgeStore):
        store.save_continuity_log("连续性记录内容。")
        ctx = store.build_context()
        assert "连续性记录内容" in ctx


# ── save_world / save_character / save_outline 原子写 ───────

class TestOtherSavesAtomic:
    def test_save_world_no_tmp(self, store: KnowledgeStore):
        store.save_world("settings", "内容")
        assert list(store.world_dir.glob("*.tmp")) == []

    def test_save_character_no_tmp(self, store: KnowledgeStore):
        store.save_character("林黛玉", "角色档案")
        assert list(store.char_dir.glob("*.tmp")) == []
        assert store.load_character("林黛玉") == "角色档案"

    def test_save_outline_no_tmp(self, store: KnowledgeStore):
        store.save_outline("大纲")
        assert list(store.story_dir.glob("*.tmp")) == []
        assert store.load_outline() == "大纲"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
