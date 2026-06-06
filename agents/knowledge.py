"""
📚 知识库 — 世界观/角色/故事的知识管理
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class KnowledgeStore:
    """知识库管理器 — 读写世界观、角色、故事知识."""

    def __init__(self, base_dir: str):
        self.base = Path(base_dir)
        self.world_dir = self.base / "world"
        self.char_dir = self.base / "characters"
        self.story_dir = self.base / "story"
        self.chapters_dir = self.story_dir / "chapters"
        self.revisions_dir = self.story_dir / "revisions"

        for d in [self.world_dir, self.char_dir, self.chapters_dir, self.revisions_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ── 世界观 ─────────────────────────────────────────────────

    def save_world(self, name: str, content: str):
        """保存世界观文档."""
        filepath = self.world_dir / f"{name}.md"
        filepath.write_text(content, encoding="utf-8")

    def load_world(self, name: str = "settings") -> str:
        """加载世界观文档."""
        filepath = self.world_dir / f"{name}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    def list_world_docs(self) -> list[str]:
        """列出所有世界观文档."""
        return [f.stem for f in self.world_dir.glob("*.md")]

    def get_world_summary(self) -> str:
        """获取所有世界观文档摘要."""
        parts = []
        for doc in sorted(self.world_dir.glob("*.md")):
            content = doc.read_text(encoding="utf-8")
            # Take first 500 chars as summary
            summary = content[:500] + ("..." if len(content) > 500 else "")
            parts.append(f"## {doc.stem}\n{summary}")
        return "\n\n".join(parts)

    # ── 角色 ───────────────────────────────────────────────────

    def save_character(self, name: str, content: str):
        """保存角色档案."""
        safe_name = self._safe_name(name)
        filepath = self.char_dir / f"{safe_name}.md"
        filepath.write_text(content, encoding="utf-8")

    def load_character(self, name: str) -> str:
        """加载角色档案."""
        safe_name = self._safe_name(name)
        filepath = self.char_dir / f"{safe_name}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        # Try fuzzy match
        for f in self.char_dir.glob("*.md"):
            if name.lower() in f.stem.lower():
                return f.read_text(encoding="utf-8")
        return ""

    def list_characters(self) -> list[str]:
        """列出所有角色."""
        return [f.stem for f in self.char_dir.glob("*.md")]

    def get_all_character_summaries(self) -> str:
        """获取所有角色的摘要."""
        parts = []
        for f in sorted(self.char_dir.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            lines = content.split("\n")
            # Extract name and core traits
            name = f.stem
            traits = ""
            for line in lines:
                if "核心特质" in line or "Core Traits" in line:
                    traits = line.strip()
                    break
            summary = content[:300] + ("..." if len(content) > 300 else "")
            parts.append(f"## {name}\n{traits}\n{summary}")
        return "\n\n".join(parts)

    # ── 章节 ───────────────────────────────────────────────────

    def save_chapter(self, chapter_num: int, content: str, author: str = "scene_writer"):
        """保存章节."""
        filepath = self.chapters_dir / f"chapter_{chapter_num:03d}.md"
        filepath.write_text(content, encoding="utf-8")
        # Also save revision history
        rev_path = self.revisions_dir / f"chapter_{chapter_num:03d}"
        rev_path.mkdir(parents=True, exist_ok=True)
        rev_file = rev_path / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{author}.md"
        rev_file.write_text(content, encoding="utf-8")

    def load_chapter(self, chapter_num: int) -> str:
        """加载章节."""
        filepath = self.chapters_dir / f"chapter_{chapter_num:03d}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    def list_chapters(self) -> list[int]:
        """列出所有已有章节号."""
        chapters = []
        for f in self.chapters_dir.glob("chapter_*.md"):
            try:
                num = int(f.stem.replace("chapter_", ""))
                chapters.append(num)
            except ValueError:
                pass
        return sorted(chapters)

    def get_all_chapters_text(self) -> str:
        """获取所有章节全文."""
        parts = []
        for num in self.list_chapters():
            content = self.load_chapter(num)
            parts.append(f"# 第 {num} 章\n\n{content}")
        return "\n\n---\n\n".join(parts)

    # ── 大纲 ───────────────────────────────────────────────────

    def save_outline(self, content: str):
        """保存故事大纲."""
        filepath = self.story_dir / "outline.md"
        filepath.write_text(content, encoding="utf-8")

    def load_outline(self) -> str:
        """加载故事大纲."""
        filepath = self.story_dir / "outline.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    # ── 连续性日志 ─────────────────────────────────────────────

    def save_continuity_log(self, content: str):
        """保存连续性检查日志."""
        filepath = self.story_dir / "continuity_log.md"
        filepath.write_text(content, encoding="utf-8")

    def load_continuity_log(self) -> str:
        """加载连续性日志."""
        filepath = self.story_dir / "continuity_log.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    # ── 上下文构建 ─────────────────────────────────────────────

    def build_context(self, chapter_num: int | None = None) -> str:
        """构建送给 Agent 的完整知识上下文."""
        parts = []

        # 世界观
        world_summary = self.get_world_summary()
        if world_summary:
            parts.append("## 🌍 世界观设定\n" + world_summary)

        # 角色
        chars = self.get_all_character_summaries()
        if chars:
            parts.append("## 👤 角色档案\n" + chars)

        # 大纲
        outline = self.load_outline()
        if outline:
            parts.append("## 📋 故事大纲\n" + outline)

        # 已有章节摘要
        chapters = self.list_chapters()
        if chapters:
            chapter_summaries = []
            for num in chapters:
                if chapter_num and num == chapter_num:
                    continue
                content = self.load_chapter(num)
                first_para = content.strip().split("\n\n")[0] if content else ""
                chapter_summaries.append(f"第 {num} 章: {first_para[:200]}...")
            if chapter_summaries:
                parts.append("## 📖 已完成的章节\n" + "\n".join(chapter_summaries))

        # 连续性日志
        cl = self.load_continuity_log()
        if cl:
            parts.append("## 🔍 连续性记录\n" + cl[-1000:])

        return "\n\n".join(parts)

    def _safe_name(self, name: str) -> str:
        """清理文件名."""
        import re
        return re.sub(r'[^\w\u4e00-\u9fff-]', '_', name.strip())


def create_knowledge_store(base_dir: str) -> KnowledgeStore:
    return KnowledgeStore(base_dir)
