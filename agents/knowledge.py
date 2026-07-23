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

from agents.llm_client import LLM_ERROR_PREFIX as _LLM_ERROR_PREFIX

logger = logging.getLogger(__name__)

# C5 修复：调研文档的输出优先级顺序，避免 sorted(glob) 字母序导致 highlights /
# creation_techniques 抢占预算、把 similar_novels 挤出窗口。
# 与 agents/topic_researcher.DEFAULT_TOPICS 的顺序保持一致。
_RESEARCH_PRIORITY = ["hot_events", "important_events", "similar_novels", "creation_techniques"]

# M8 修复：拒绝写入 KB 的错误占位符前缀（与 _LLM_ERROR_PREFIX 互补，覆盖中文化占位）
_RESEARCH_ERROR_MARKERS = ("（调研综合失败", "（生成失败")


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """原子写：写到 tmp 文件后 os.replace 到目标，避免崩溃留下半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)


class KnowledgeStore:
    """Two-tier knowledge store (series + variant)."""

    def __init__(self, base_dir: str, series_dir: str = "", series_research_dir: str = ""):
        self.base = Path(base_dir)
        self.series = Path(series_dir) if series_dir else None
        self.series_research = Path(series_research_dir) if series_research_dir else None

        self.world_dir = self.base / "world"
        self.char_dir = self.base / "characters"
        self.story_dir = self.base / "story"
        self.chapters_dir = self.story_dir / "chapters"
        self.revisions_dir = self.story_dir / "revisions"
        self.summaries_dir = self.story_dir / "summaries"
        self.research_dir = self.base / "research"

        for d in [self.world_dir, self.char_dir, self.chapters_dir,
                  self.revisions_dir, self.summaries_dir, self.research_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # M7 修复：缓存全量拼接结果，键为 (目录最新 mtime, 参数)，save 时失效。
        # 写作阶段每章 build_context 都会读，缓存可避免重复磁盘 IO。
        self._research_cache: tuple[float, str, str] | None = None  # (mtime, args_key, content)
        self._series_cache: tuple[float, str] | None = None  # (mtime, content)
        self._world_summary_cache: tuple[float, str] | None = None  # (mtime, content)

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
        # M7: 缓存基于 series 目录 mtime
        mtime = self._dir_mtime(self.series)
        cache = self._series_cache
        if cache is not None and cache[0] == mtime:
            return cache[1]
        parts = []
        for doc in self._series_md_files():
            content = doc.read_text(encoding="utf-8")
            parts.append(f"### [Series] {doc.stem}\n\n{content}")
        result = "\n\n---\n\n".join(parts)
        self._series_cache = (mtime, result)
        return result

    def list_series_docs(self) -> list[str]:
        return [f.stem for f in self._series_md_files()]

    # ── World docs (variant layer, read-write) ─────────────────

    def save_world(self, name: str, content: str):
        filepath = self.world_dir / f"{name}.md"
        _atomic_write_text(filepath, content)
        # M7: 失效 world_summary 缓存
        self._world_summary_cache = None

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
        # M7: 缓存基于 (variant world mtime, series mtime)
        v_mtime = self._dir_mtime(self.world_dir)
        s_mtime = self._dir_mtime(self.series)
        cache_key = f"{v_mtime}:{s_mtime}"
        cache = self._world_summary_cache
        if cache is not None and cache[0] == cache_key:
            return cache[1]
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
        result = "\n\n".join(parts)
        self._world_summary_cache = (cache_key, result)
        return result

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

    def is_chapter_delivered(self, chapter_num: int) -> bool:
        """章节是否已交付（有摘要文件 = 走完了 PASS/耗尽流程）。

        summaries/chapter_NNN.md 只在 _generate_chapter_summary 成功时写入
        （PASS 或耗尽轮次路径），比检查 chapter_NNN.md 更准确（后者每轮修订都写）。
        供断点续跑的写作循环跳过已完成章节。
        """
        return (self.summaries_dir / f"chapter_{chapter_num:03d}.md").exists()

    # ── Research KB (variant + series, read-write variant / read-only series) ──

    def _safe_topic(self, topic: str) -> str:
        """调研主题 → 文件名 slug（与 _safe_name 同语义，复用实现）。"""
        return self._safe_name(topic)

    def _dir_mtime(self, d: Path | None) -> float:
        """目录最新 mtime（文件 mtime 的 max，空目录返回 0）。用于缓存键。"""
        if not d or not d.exists():
            return 0.0
        try:
            return max(f.stat().st_mtime for f in d.glob("*.md"))
        except (OSError, ValueError):
            return 0.0

    def _series_research_files(self) -> list[Path]:
        if not self.series_research or not self.series_research.exists():
            return []
        return sorted(self.series_research.glob("*.md"))

    def save_research(self, topic: str, content: str) -> None:
        """写入变体级调研文档 research/{topic}.md（原子写）。

        M8 修复：若 content 是 LLM 失败占位符（_LLM_ERROR_PREFIX 或中文化的
        「调研综合失败」/「生成失败」），拒绝写入并警告，避免错误信息污染 KB
        被下游 build_context 注入到所有 agent 的 prompt。
        """
        if not content:
            logger.warning("跳过写入调研文档（空内容）: %s", topic)
            return
        if content.lstrip().startswith(_LLM_ERROR_PREFIX) or any(
            marker in content for marker in _RESEARCH_ERROR_MARKERS
        ):
            logger.warning("跳过写入调研文档（错误占位符）: %s", topic)
            return
        filepath = self.research_dir / f"{self._safe_topic(topic)}.md"
        _atomic_write_text(filepath, content)
        # M7: 写入后失效 research 缓存
        self._research_cache = None

    def load_research(self, topic: str) -> str:
        """读取调研文档，变体层缺失时 fallback 系列层。"""
        filepath = self.research_dir / f"{self._safe_topic(topic)}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        if self.series_research:
            spath = self.series_research / f"{self._safe_topic(topic)}.md"
            if spath.exists():
                return spath.read_text(encoding="utf-8")
        return ""

    def list_research_topics(self) -> list[str]:
        """变体 + 系列层调研文档合并去重。"""
        topics: set[str] = set()
        for f in self.research_dir.glob("*.md"):
            topics.add(f.stem)
        for f in self._series_research_files():
            topics.add(f.stem)
        return sorted(topics)

    def get_all_research(self, max_per_doc: int = 2000, total_budget: int = 6000) -> str:
        """拼接所有调研文档，每篇截断到 max_per_doc 字，总和截断到 total_budget。

        优先级：变体层在前（更相关），系列层在后。变体同名主题覆盖系列。

        C3 修复：highlights 是 Innovator 的产物，不应作为调研输入再喂回下游 agent，
        这里显式排除 highlights slug，避免自注入。
        C5 修复：变体层按 _RESEARCH_PRIORITY 顺序输出，确保重要主题优先占用预算。
        M7 修复：基于 (variant mtime, series mtime) 缓存拼接结果，每章 build_context 复用。
        """
        # M7: 缓存命中检查
        v_mtime = self._dir_mtime(self.research_dir)
        s_mtime = self._dir_mtime(self.series_research)
        args_key = f"{max_per_doc}:{total_budget}"
        cache = self._research_cache
        if cache is not None and cache[0] == f"{v_mtime}:{s_mtime}" and cache[1] == args_key:
            return cache[2]

        parts: list[str] = []
        total = 0
        seen: set[str] = set()

        # 变体层：按优先级顺序输出已知主题，再输出其他主题
        variant_files = {f.stem: f for f in self.research_dir.glob("*.md")}
        ordered_stems: list[str] = []
        for slug in _RESEARCH_PRIORITY:
            if slug in variant_files and slug != "highlights":
                ordered_stems.append(slug)
        for stem in sorted(variant_files.keys()):
            if stem not in ordered_stems and stem != "highlights":
                ordered_stems.append(stem)

        for stem in ordered_stems:
            f = variant_files[stem]
            seen.add(stem)
            content = f.read_text(encoding="utf-8")
            # 按剩余预算截断
            remaining = total_budget - total
            if remaining <= 0:
                break
            truncated = content[:min(max_per_doc, remaining)]
            parts.append(f"### [Research/variant] {stem}\n\n{truncated}")
            total += len(truncated)

        # 系列层（未与变体重名，且排除 highlights）
        if total < total_budget:
            for f in self._series_research_files():
                if f.stem in seen or f.stem == "highlights":
                    continue
                remaining = total_budget - total
                if remaining <= 0:
                    break
                content = f.read_text(encoding="utf-8")
                truncated = content[:min(max_per_doc, remaining)]
                parts.append(f"### [Research/series] {f.stem}\n\n{truncated}")
                total += len(truncated)

        result = "\n\n---\n\n".join(parts)
        # M7: 填充缓存
        self._research_cache = (f"{v_mtime}:{s_mtime}", args_key, result)
        return result

    def load_series_research(self) -> str:
        """仅系列层调研（供需要明确区分优先级的场景）。"""
        parts: list[str] = []
        for f in self._series_research_files():
            content = f.read_text(encoding="utf-8")
            parts.append(f"### [Research/series] {f.stem}\n\n{content}")
        return "\n\n---\n\n".join(parts)

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

        # Research KB (variant + series)：调研沉淀，写作 / 创新阶段参考
        research = self.get_all_research()
        if research:
            parts.append("## 调研知识库\n" + research)

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
                # O(n) 一次扫描：累加前缀和，找到不超过 max_chars 的最大尾部切片。
                # 旧实现用 while + pop(0)，pop(0) 是 O(n)，整体 O(n²)，
                # 100+ 章长篇会累积可观开销。
                prefix = 0
                prefix_sums = [0]
                for s in chapter_summaries:
                    prefix += len(s)
                    prefix_sums.append(prefix)
                total = prefix_sums[-1]
                keep_from = 0
                if total > max_chars:
                    # 从尾部保留尽可能多的最新摘要，丢弃最旧的若干条
                    # 找最小的 keep_from 使 sum(chapter_summaries[keep_from:]) <= max_chars
                    # 等价于：prefix_sums[-1] - prefix_sums[keep_from] <= max_chars
                    target = total - max_chars
                    # 二分找第一个 prefix_sums[k] >= target
                    import bisect
                    keep_from = bisect.bisect_left(prefix_sums, target)
                    if keep_from > 0 and len(chapter_summaries) > 1:
                        chapter_summaries = chapter_summaries[keep_from:]
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


def create_knowledge_store(
    base_dir: str, series_dir: str = "", series_research_dir: str = ""
) -> KnowledgeStore:
    return KnowledgeStore(base_dir, series_dir, series_research_dir)