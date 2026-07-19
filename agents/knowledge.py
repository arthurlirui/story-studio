"""
KnowledgeStore - Two-tier knowledge system (series + variant)

Series layer (series_dir): shared worldview, profession spectrum, conflict engines
Variant layer (base_dir): per-novel unique worldview, characters, knowledge

Priority: variant > series. Same-name docs: variant overrides series.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class KnowledgeStore:
    """Two-tier knowledge store (series + variant)."""

    def __init__(self, base_dir: str, series_dir: str = ""):
        self.base = Path(base_dir)
        self.series = Path(series_dir) if series_dir else None

        self.world_dir = self.base / "world"
        self.char_dir = self.base / "characters"
        self.story_dir = self.base / "story"
        self.chapters_dir = self.story_dir / "chapters"
        self.revisions_dir = self.story_dir / "revisions"

        for d in [self.world_dir, self.char_dir, self.chapters_dir, self.revisions_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ── Series layer (read-only) ───────────────────────────────

    def _series_md_files(self) -> list[Path]:
        if not self.series or not self.series.exists():
            return []
        return sorted(self.series.glob("*.md"))

    def load_series_knowledge(self, name: str) -> str:
        if not self.series:
            return ""
        filepath = self.series / f"{name}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    def get_all_series_knowledge(self) -> str:
        parts = []
        for doc in self._series_md_files():
            content = doc.read_text(encoding="utf-8")
            parts.append(f"### [Series] {doc.stem}\n\n{content}")
        return "\n\n---\n\n".join(parts)

    def list_series_docs(self) -> list[str]:
        return [f.stem for f in self._series_md_files()]

    # ── World docs (variant layer, read-write) ─────────────────

    def save_world(self, name: str, content: str):
        filepath = self.world_dir / f"{name}.md"
        filepath.write_text(content, encoding="utf-8")

    def load_world(self, name: str = "settings") -> str:
        filepath = self.world_dir / f"{name}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return self.load_series_knowledge(name)

    def list_world_docs(self) -> list[str]:
        docs = set()
        for f in self.world_dir.glob("*.md"):
            docs.add(f.stem)
        for f in self._series_md_files():
            docs.add(f.stem)
        return sorted(docs)

    def get_world_summary(self) -> str:
        parts = []
        seen = set()
        for doc in sorted(self.world_dir.glob("*.md")):
            seen.add(doc.stem)
            content = doc.read_text(encoding="utf-8")
            summary = content[:500] + ("..." if len(content) > 500 else "")
            parts.append(f"## {doc.stem} (variant)\n{summary}")
        for doc in self._series_md_files():
            if doc.stem in seen:
                continue
            seen.add(doc.stem)
            content = doc.read_text(encoding="utf-8")
            summary = content[:500] + ("..." if len(content) > 500 else "")
            parts.append(f"## {doc.stem} (series)\n{summary}")
        return "\n\n".join(parts)

    # ── Characters ─────────────────────────────────────────────

    def save_character(self, name: str, content: str):
        safe_name = self._safe_name(name)
        filepath = self.char_dir / f"{safe_name}.md"
        filepath.write_text(content, encoding="utf-8")

    def load_character(self, name: str) -> str:
        safe_name = self._safe_name(name)
        filepath = self.char_dir / f"{safe_name}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        for f in self.char_dir.glob("*.md"):
            if name.lower() in f.stem.lower():
                return f.read_text(encoding="utf-8")
        return ""

    def list_characters(self) -> list[str]:
        return [f.stem for f in self.char_dir.glob("*.md")]

    def get_all_character_summaries(self) -> str:
        parts = []
        for f in sorted(self.char_dir.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            lines = content.split("\n")
            name = f.stem
            traits = ""
            for line in lines:
                if "\u6838\u5fc3\u7279\u8d28" in line or "Core Traits" in line:
                    traits = line.strip()
                    break
            summary = content[:300] + ("..." if len(content) > 300 else "")
            parts.append(f"## {name}\n{traits}\n{summary}")
        return "\n\n".join(parts)

    # ── Chapters ───────────────────────────────────────────────

    def save_chapter(self, chapter_num: int, content: str, author: str = "scene_writer"):
        filepath = self.chapters_dir / f"chapter_{chapter_num:03d}.md"
        filepath.write_text(content, encoding="utf-8")
        rev_path = self.revisions_dir / f"chapter_{chapter_num:03d}"
        rev_path.mkdir(parents=True, exist_ok=True)
        rev_file = rev_path / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{author}.md"
        rev_file.write_text(content, encoding="utf-8")

    def load_chapter(self, chapter_num: int) -> str:
        filepath = self.chapters_dir / f"chapter_{chapter_num:03d}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    def list_chapters(self) -> list[int]:
        chapters = []
        for f in self.chapters_dir.glob("chapter_*.md"):
            try:
                num = int(f.stem.replace("chapter_", ""))
                chapters.append(num)
            except ValueError:
                pass
        return sorted(chapters)

    def get_all_chapters_text(self) -> str:
        parts = []
        for num in self.list_chapters():
            content = self.load_chapter(num)
            parts.append(f"# Chapter {num}\n\n{content}")
        return "\n\n---\n\n".join(parts)

    # ── Outline ────────────────────────────────────────────────

    def save_outline(self, content: str):
        filepath = self.story_dir / "outline.md"
        filepath.write_text(content, encoding="utf-8")

    def load_outline(self) -> str:
        filepath = self.story_dir / "outline.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    # ── Continuity log ─────────────────────────────────────────

    def save_continuity_log(self, content: str):
        filepath = self.story_dir / "continuity_log.md"
        filepath.write_text(content, encoding="utf-8")

    def load_continuity_log(self) -> str:
        filepath = self.story_dir / "continuity_log.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    # ── Context builder (two-tier merge) ───────────────────────

    def build_context(self, chapter_num: int | None = None) -> str:
        """Build full context for agents: series knowledge + variant knowledge."""
        parts = []

        # Series layer: shared knowledge (profession spectrum, conflict engines, etc.)
        series_knowledge = self.get_all_series_knowledge()
        if series_knowledge:
            parts.append("## Series Knowledge (shared)\n" + series_knowledge)

        # Variant layer: this novel's unique worldview
        world_summary = self.get_world_summary()
        if world_summary:
            parts.append("## World Setting (this novel)\n" + world_summary)

        # Characters
        chars = self.get_all_character_summaries()
        if chars:
            parts.append("## Characters\n" + chars)

        # Outline
        outline = self.load_outline()
        if outline:
            parts.append("## Outline\n" + outline)

        # Previous chapters
        chapters = self.list_chapters()
        if chapters:
            chapter_summaries = []
            for num in chapters:
                if chapter_num and num == chapter_num:
                    continue
                content = self.load_chapter(num)
                first_para = content.strip().split("\n\n")[0] if content else ""
                chapter_summaries.append(f"Ch {num}: {first_para[:200]}...")
            if chapter_summaries:
                parts.append("## Completed Chapters\n" + "\n".join(chapter_summaries))

        # Continuity log
        cl = self.load_continuity_log()
        if cl:
            parts.append("## Continuity Log\n" + cl[-1000:])

        # Priority notice
        parts.append("## Priority\nVariant knowledge > Series knowledge. When conflicting, variant wins.")

        return "\n\n".join(parts)

    def _safe_name(self, name: str) -> str:
        """Sanitize filename."""
        import re
        return re.sub(r'[^\w\u4e00-\u9fff-]', '_', name.strip())


def create_knowledge_store(base_dir: str, series_dir: str = "") -> KnowledgeStore:
    return KnowledgeStore(base_dir, series_dir)