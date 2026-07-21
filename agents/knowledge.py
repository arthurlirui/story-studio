"""
KnowledgeStore - Two-tier knowledge system (series + variant)

Series layer (series_dir): shared worldview, profession spectrum, conflict engines
Variant layer (base_dir): per-novel unique worldview, characters, knowledge

Priority: variant > series. Same-name docs: variant overrides series.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 连续性日志的 API 错误哨兵前缀（与 agents/llm_client._ERROR_SENTINEL 一致）
_LLM_ERROR_PREFIX = "[LLM API error"


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """原子写：写到 tmp 文件后 os.replace 到目标，避免崩溃留下半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)


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
        self.summaries_dir = self.story_dir / "summaries"

        for d in [self.world_dir, self.char_dir, self.chapters_dir,
                  self.revisions_dir, self.summaries_dir]:
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
        _atomic_write_text(filepath, content)

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
        _atomic_write_text(filepath, content)

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
        _atomic_write_text(filepath, content)
        rev_path = self.revisions_dir / f"chapter_{chapter_num:03d}"
        rev_path.mkdir(parents=True, exist_ok=True)
        rev_file = rev_path / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{author}.md"
        _atomic_write_text(rev_file, content)

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
        _atomic_write_text(filepath, content)

    def load_outline(self) -> str:
        filepath = self.story_dir / "outline.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    # ── Chapter reviews (自动修订审计) ─────────────────────────

    def save_chapter_review(
        self, chapter_num: int, round_n: int, verdict: str, review: str
    ) -> None:
        """保存某一章某一轮的评审记录到 story/reviews/chapter_NNN_review.json。"""
        import json as _json
        reviews_dir = self.story_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        filepath = reviews_dir / f"chapter_{chapter_num:03d}_review.json"
        # 追加到既有列表（同一章可能多轮）
        existing: list = []
        if filepath.exists():
            try:
                existing = _json.loads(filepath.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except (_json.JSONDecodeError, ValueError):
                existing = []
        existing.append({
            "round": round_n,
            "verdict": verdict,
            "review": review,
            "timestamp": datetime.now().isoformat(),
        })
        _atomic_write_text(filepath, _json.dumps(existing, ensure_ascii=False, indent=2))

    def load_chapter_reviews(self, chapter_num: int) -> list[dict]:
        """读取某一章的所有评审记录。"""
        import json as _json
        filepath = self.story_dir / "reviews" / f"chapter_{chapter_num:03d}_review.json"
        if not filepath.exists():
            return []
        try:
            data = _json.loads(filepath.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (_json.JSONDecodeError, ValueError):
            return []

    # ── Continuity log ─────────────────────────────────────────

    def save_continuity_log(self, content: str):
        # 守卫：API 失败返回的哨兵串不应污染连续性日志（会被每章 build_context 拉入）
        if not content or content.startswith(_LLM_ERROR_PREFIX):
            logger.warning("跳过写入连续性日志（内容为空或 LLM API 错误哨兵）: %s", (content or "")[:120])
            return
        filepath = self.story_dir / "continuity_log.md"
        _atomic_write_text(filepath, content)

    def load_continuity_log(self) -> str:
        filepath = self.story_dir / "continuity_log.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    # ── Batch briefs (并行批次协调简报) ────────────────────────

    def save_batch_brief(self, batch_id: str, data: dict) -> None:
        """持久化批次简报到 story/batch_briefs/<batch_id>.json 供事后审计。"""
        import json as _json
        briefs_dir = self.story_dir / "batch_briefs"
        briefs_dir.mkdir(parents=True, exist_ok=True)
        filepath = briefs_dir / f"{batch_id}.json"
        _atomic_write_text(filepath, _json.dumps(data, ensure_ascii=False, indent=2))

    def load_batch_brief(self, batch_id: str) -> dict:
        """读取某批次简报，不存在返回空字典。"""
        import json as _json
        filepath = self.story_dir / "batch_briefs" / f"{batch_id}.json"
        if not filepath.exists():
            return {}
        try:
            return _json.loads(filepath.read_text(encoding="utf-8"))
        except (_json.JSONDecodeError, ValueError):
            return {}

    # ── Chapter summaries ──────────────────────────────────────

    def save_chapter_summary(self, chapter_num: int, summary: str) -> None:
        """保存章节摘要（≤200 字）到 story/summaries/chapter_NNN.md。"""
        if not summary or summary.startswith(_LLM_ERROR_PREFIX):
            logger.warning("跳过写入章节摘要（空或 LLM 错误哨兵）: Ch%d", chapter_num)
            return
        filepath = self.summaries_dir / f"chapter_{chapter_num:03d}.md"
        _atomic_write_text(filepath, summary)

    def load_chapter_summary(self, chapter_num: int) -> str:
        """读取某一章的摘要，不存在返回空串。"""
        filepath = self.summaries_dir / f"chapter_{chapter_num:03d}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return ""

    def list_chapter_summaries(self) -> list[int]:
        """返回有摘要的章节号列表（升序）。"""
        import re
        nums: list[int] = []
        if not self.summaries_dir.exists():
            return nums
        for f in self.summaries_dir.glob("chapter_*.md"):
            m = re.match(r'chapter_(\d+)\.md', f.name)
            if m:
                nums.append(int(m.group(1)))
        return sorted(nums)

    # ── Context builder (two-tier merge) ───────────────────────

    def build_context(self, chapter_num: int | None = None,
                      max_chars: int = 60000) -> str:
        """Build full context for agents: series knowledge + variant knowledge.

        章节历史用摘要（save_chapter_summary 存的 ≤200 字）替代首段 200 字；
        无摘要时回退到首段。总长度超 max_chars 时按章节号倒序裁掉最旧摘要。
        """
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

        # Outline（截断到 8000 字，避免超长大纲吃掉预算）
        outline = self.load_outline()
        if outline:
            parts.append("## Outline\n" + outline[:8000])

        # Previous chapters — 优先用摘要，无摘要回退首段
        chapters = self.list_chapters()
        if chapters:
            chapter_summaries: list[str] = []
            for num in chapters:
                if chapter_num and num == chapter_num:
                    continue
                summary = self.load_chapter_summary(num)
                if summary:
                    chapter_summaries.append(f"Ch {num}: {summary}")
                else:
                    content = self.load_chapter(num)
                    first_para = content.strip().split("\n\n")[0] if content else ""
                    chapter_summaries.append(f"Ch {num}: {first_para[:200]}...")
            # 预算裁剪：总长超 max_chars 时从最旧的章节摘要开始丢弃
            if chapter_summaries:
                total = sum(len(s) for s in chapter_summaries)
                while total > max_chars and len(chapter_summaries) > 1:
                    dropped = chapter_summaries.pop(0)  # 最旧
                    total -= len(dropped)
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