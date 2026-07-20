"""
🎭 编排器 (Orchestrator) — 多 Agent 协作工作流引擎

协调整个创作流程：策划→建立→大纲→写作→修订
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import StudioConfig, load_config
from agents import (
    Showrunner, WorldArchitect, CharacterDesigner,
    SceneWriter, Editor, LiteraryAdvisor, ContinuityKeeper,
    TitleDesigner, Hooker, ClimaxDesigner,
    KnowledgeStore,
)
from agents.llm_client import client as llm_client
from agents.text_cleaner import clean_chapter_body, strip_existing_title

logger = logging.getLogger(__name__)

# 完稿阶段默认作者署名
DEFAULT_AUTHOR = "独孤元景 著"
# 封面工具脚本路径（相对项目根）
_COVER_TOOL = Path(__file__).resolve().parent / "tools" / "book_cover_comfy.py"


def _truncate_at_sentence(text: str, max_len: int) -> str:
    """把超长文本截断到 ≤ max_len，优先在句末标点处断开。

    在前 max_len 字符内倒序找最近的句末标点（。！？；.!?），
    找到且位置不早于 max_len 的一半，则截到该标点之后；
    否则硬截断到 max_len。
    """
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    for sep in ("。", "！", "？", "；", ".", "!", "?"):
        idx = cut.rfind(sep)
        if idx >= max_len // 2:
            return cut[: idx + 1]
    return cut


class StoryOrchestrator:
    """
    创作编排器 — Agent 团队的指挥中心.

    Phases:
        planning    → 策划阶段 (接收需求, 分析, 团队讨论)
        building    → 建立阶段 (世界观, 角色)
        outlining   → 大纲阶段 (章节大纲)
        writing     → 写作阶段 (逐章写作 + 润色 + 检查)
        revision    → 修订阶段 (基于反馈修改)
        complete    → 完成
    """

    def __init__(
        self,
        config: StudioConfig | None = None,
        client: Any = None,
    ):
        self.cfg = config or load_config()
        self.client = client or llm_client
        if self.client is None:
            raise RuntimeError(
                "LLM client 未初始化。请先调用 agents.llm_client.init_client()，"
                "或在构造 StoryOrchestrator 时传入 client 参数。"
            )

        # Knowledge store (two-tier: series + variant)
        self.knowledge = KnowledgeStore(
            self.cfg.knowledge_dir,
            self.cfg.series_knowledge_dir,
        )

        # Create agents — all use LLM API
        self.showrunner = Showrunner(
            "总策划", "Showrunner", "主持创作流程, 分配任务, 评审产出",
            self.client, model=self.cfg.main_model, temperature=0.6,
        )
        self.world_architect = WorldArchitect(
            "世界观架构师", "World Architect", "构建世界观设定",
            self.client, model=self.cfg.main_model, temperature=0.8,
        )
        self.character_designer = CharacterDesigner(
            "角色设计师", "Character Designer", "创建角色档案",
            self.client, model=self.cfg.main_model, temperature=0.8,
        )
        # Multiple Scene Writers for parallel chapter writing (at least 1)
        self.scene_writers: list[SceneWriter] = []
        writer_count = max(1, self.cfg.scene_writers)
        for i in range(writer_count):
            sw = SceneWriter(
                f"场景编剧{i + 1}", "Scene Writer", f"核心写作 #{i + 1}",
                self.client, model=self.cfg.main_model, temperature=0.9, max_tokens=8192,
            )
            self.scene_writers.append(sw)
        self.editor = Editor(
            "编辑", "Editor", "文字润色",
            self.client, model=self.cfg.main_model, temperature=0.5,
        )
        self.literary_advisor = LiteraryAdvisor(
            "文学顾问", "Literary Advisor", "文学技巧建议",
            self.client, model=self.cfg.main_model, temperature=0.7,
        )
        self.continuity_keeper = ContinuityKeeper(
            "连续性检查员", "Continuity Keeper", "一致性检查",
            self.client, model=self.cfg.main_model, temperature=0.4,
        )
        # Specialist designers (网文标题/钩子/爽点)
        self.title_designer = TitleDesigner(
            "标题设计师", "Title Designer", "设计书名/章节标题",
            self.client, model=self.cfg.main_model, temperature=0.8,
        )
        self.hooker = Hooker(
            "钩子设计师", "Hooker", "设计章节钩子",
            self.client, model=self.cfg.main_model, temperature=0.8,
        )
        self.climax_designer = ClimaxDesigner(
            "爽点设计师", "Climax Designer", "设计爽点与高潮",
            self.client, model=self.cfg.main_model, temperature=0.8,
        )

        self.agents = {
            "showrunner": self.showrunner,
            "world_architect": self.world_architect,
            "character_designer": self.character_designer,
            "editor": self.editor,
            "literary_advisor": self.literary_advisor,
            "continuity_keeper": self.continuity_keeper,
            "title_designer": self.title_designer,
            "hooker": self.hooker,
            "climax_designer": self.climax_designer,
        }
        # Add scene writers individually
        for i, sw in enumerate(self.scene_writers):
            self.agents[f"scene_writer_{i + 1}"] = sw

        # Project state
        self.project_name: str = ""
        self.phase: str = "idle"
        self.current_chapter: int = 0
        self.total_chapters: int = 0
        self.conversation_log: list[dict] = []
        self._call_count: int = 0

    async def _rate_limit_pause(self):
        """在连续 API 调用之间插入延迟，避免触发限流."""
        self._call_count += 1
        if self._call_count > 1:
            await asyncio.sleep(3.0)  # 3s between calls

    # ── Phase 1: 策划 ──────────────────────────────────────────

    async def phase_planning(self, user_request: str) -> str:
        """策划阶段: 接收用户需求，生成创作企划."""
        self.phase = "planning"
        self._log("user", user_request)

        # Showrunner 分析需求
        plan = await self.showrunner.think(
            f"用户提出了以下创作需求，请分析并生成创作企划框架。\n\n"
            f"## 用户需求\n{user_request}\n\n"
            f"请输出包含以下内容的企划框架:\n"
            f"1. 作品类型/基调\n"
            f"2. 核心设定方向（世界观类型、时代背景）\n"
            f"3. 核心角色需求（主角类型、关键配角）\n"
            f"4. 故事主线方向\n"
            f"5. 建议章节数\n"
            f"6. 目标读者/受众"
        )
        self._log("showrunner", plan)

        # Team discussion
        discussion = await self._team_discussion(
            f"基于以下企划框架, 请世界观架构师和角色设计师分别给出初步建议。\n\n{plan}"
        )

        # Final plan
        final_plan = await self.showrunner.think(
            f"综合团队讨论结果，请输出最终的创作企划书。\n\n"
            f"初始企划:\n{plan}\n\n"
            f"团队讨论:\n{discussion}"
        )
        self._log("showrunner", final_plan)

        # Save
        self.knowledge.save_world("plan", final_plan)
        return final_plan

    # ── Phase 2: 建立 ──────────────────────────────────────────

    async def phase_building(self) -> str:
        """建立阶段: 世界观 + 角色设定."""
        self.phase = "building"
        plan = self.knowledge.load_world("plan")
        context = f"项目创作企划:\n{plan}"

        # World building
        world_setting = await self.world_architect.think(
            "请根据创作企划，设计完整的世界观设定。",
            context,
        )
        self._log("world_architect", world_setting)
        self.knowledge.save_world("settings", world_setting)

        # Character design
        characters = await self.character_designer.think(
            "请根据世界观和创作企划，设计核心角色档案。\n"
            "每个角色请使用标准档案格式。",
            context + f"\n\n## 世界观设定\n{world_setting[:2000]}",
        )
        self._log("character_designer", characters)
        # Save individual characters
        self._save_characters(characters)

        # Showrunner review
        review = await self.showrunner.review(
            f"世界观设定:\n{world_setting[:2000]}\n\n角色设定:\n{characters[:2000]}",
            "请评审这些设定是否需要补充或修改。"
        )
        self._log("showrunner", review)

        return f"## 世界观\n{world_setting}\n\n## 角色\n{characters}\n\n## 评审\n{review}"

    # ── Phase 3: 大纲 ──────────────────────────────────────────

    async def phase_outlining(self, total_chapters: int | None = None) -> str:
        """大纲阶段: 生成章节大纲.

        若未显式指定章节数，尝试从企划书中解析"建议章节数"；
        解析失败则默认 10 章。
        """
        self.phase = "outlining"

        if total_chapters is None:
            plan = self.knowledge.load_world("plan")
            total_chapters = self._parse_suggested_chapters(plan) or 10
        self.total_chapters = total_chapters

        context = self.knowledge.build_context()

        outline = await self.showrunner.think(
            f"请生成 {total_chapters} 章的完整章节大纲。\n\n"
            f"每章大纲需要包含:\n"
            f"1. 章节标题\n"
            f"2. 核心事件（2-3个）\n"
            f"3. 出场角色\n"
            f"4. 章节悬念/钩子\n"
            f"5. 字数预估\n\n"
            f"注意: 整体要有起承转合，高潮章节安排在总章节的 60-80% 位置。",
            context,
        )
        self._log("showrunner", outline)

        # 专家设计：标题 / 钩子 / 爽点（三位专家依次优化大纲）
        await self._rate_limit_pause()
        title_advice = await self.title_designer.think(
            f"请为以下章节大纲设计更吸引点击的章节标题（保持章号不变，只优化标题）。\n\n{outline}",
            context,
        )
        self._log("title_designer", title_advice)

        await self._rate_limit_pause()
        hook_advice = await self.hooker.think(
            f"请为以下章节大纲的每一章设计章末钩子方案，并指出哪些章缺少有效钩子。\n\n{outline}",
            context,
        )
        self._log("hooker", hook_advice)

        await self._rate_limit_pause()
        climax_advice = await self.climax_designer.think(
            f"请审视以下章节大纲的爽点/高潮分布，指出爽点不足的章节并给出强化建议。\n\n{outline}",
            context,
        )
        self._log("climax_designer", climax_advice)

        # Literary advisor review
        await self._rate_limit_pause()
        lit_advice = await self.literary_advisor.think(
            "请分析以下章节大纲，给出结构建议。\n\n" + outline,
            context,
        )
        self._log("literary_advisor", lit_advice)

        # Final outline — 综合三位设计师 + 文学顾问的建议
        final_outline = await self.showrunner.think(
            f"结合以下专家建议，输出最终版章节大纲（含优化后的章节标题、钩子、爽点安排）。\n\n"
            f"初始大纲:\n{outline}\n\n"
            f"标题设计建议:\n{title_advice}\n\n"
            f"钩子设计建议:\n{hook_advice}\n\n"
            f"爽点设计建议:\n{climax_advice}\n\n"
            f"文学建议:\n{lit_advice}"
        )
        self._log("showrunner", final_outline)

        self.knowledge.save_outline(final_outline)

        # 从大纲中解析书名，回写 project_name（已设值则不覆盖）
        title = self._parse_book_title(final_outline)
        if title and not self.project_name:
            self.project_name = title
            logger.info("从大纲解析到书名: %s", title)

        return final_outline

    @staticmethod
    def _parse_book_title(outline: str) -> str | None:
        """从大纲文本中提取书名。返回纯书名（不含《》），解析失败返回 None。

        优先匹配 "## 推荐主标题" 区块下的第一个《...》；
        失败再回退到 "书名候选" 区块的第一个《...》。
        """
        if not outline:
            return None
        # 1. "推荐主标题" 区块：取该标题后 80 字内的第一个书名号
        m = re.search(r'推荐主标题[\s\S]{0,80}?《([^》]+)》', outline)
        if m:
            return m.group(1).strip()
        # 2. "书名候选" 区块回退
        m = re.search(r'书名候选[\s\S]{0,200}?《([^》]+)》', outline)
        if m:
            return m.group(1).strip()
        return None

    # ── Phase 4: 写作 (支持并行) ──────────────────────────────

    async def phase_writing(self, chapter_num: int | None = None) -> str:
        """写作阶段: 写一章 → 润色 → 检查 (单章模式)."""
        self.phase = "writing"

        if chapter_num:
            self.current_chapter = chapter_num
        else:
            chapters = self.knowledge.list_chapters()
            self.current_chapter = (chapters[-1] if chapters else 0) + 1

        context = self.knowledge.build_context(self.current_chapter)
        outline = self.knowledge.load_outline()

        # Step 1: Write chapter (use first scene writer)
        scene_prompt = (
            f"请撰写第 {self.current_chapter} 章。\n\n"
            f"## 大纲内容\n"
        )
        chapter_outline = self._extract_chapter_outline(outline, self.current_chapter)
        if chapter_outline:
            scene_prompt += chapter_outline
        else:
            scene_prompt += f"第 {self.current_chapter} 章（根据上下文自然推进）"

        writer = self.scene_writers[0]
        await self._rate_limit_pause()
        chapter_text = await writer.think(scene_prompt, context)
        if not chapter_text or chapter_text.startswith("[LLM API error"):
            return f"## 第 {self.current_chapter} 章 ❌ 写作失败\n\n{chapter_text}"
        self._log("scene_writer", f"Chapter {self.current_chapter}: {chapter_text[:100]}...")
        self.knowledge.save_chapter(self.current_chapter, chapter_text, "scene_writer")

        # Step 2: Editor polish
        await self._rate_limit_pause()
        edited = await self.editor.think(
            f"请润色第 {self.current_chapter} 章。保留所有内容, 只优化表达。\n\n" + chapter_text,
            context,
        )
        if not edited or edited.startswith("[LLM API error"):
            edited = chapter_text  # 润色失败时退回原稿
        self._log("editor", edited[:200])
        self.knowledge.save_chapter(self.current_chapter, edited, "editor")

        # Step 3: Continuity check
        await self._rate_limit_pause()
        continuity = await self.continuity_keeper.think(
            f"请检查第 {self.current_chapter} 章的一致性。\n\n" + edited,
            context,
        )
        self._log("continuity_keeper", continuity)
        self.knowledge.save_continuity_log(continuity)

        # Step 4: Showrunner review — 要求首行输出结构化 VERDICT
        await self._rate_limit_pause()
        review = await self.showrunner.think(
            f"请评审第 {self.current_chapter} 章。\n\n"
            f"## 编辑后版本\n{edited[:3000]}\n\n"
            f"## 连续性检查\n{continuity[:1000]}\n\n"
            f"## 输出格式（必须严格遵守）\n"
            f"第一行必须是 `VERDICT: PASS` 或 `VERDICT: REVISE` 或 `VERDICT: REJECT`，"
            f"之后空一行再写评审意见。PASS=通过；REVISE=需修订；REJECT=严重偏离需重写。",
        )
        self._log("showrunner", f"Review Ch{self.current_chapter}: {review[:200]}")

        verdict = self._parse_review_verdict(review)
        if verdict == "PASS":
            return f"## 第 {self.current_chapter} 章 ✅ 通过\n\n{edited}"
        elif verdict == "REJECT":
            return f"## 第 {self.current_chapter} 章 ❌ 退回重写\n\n{review}\n\n---\n\n原稿:\n{chapter_text}"
        else:
            return f"## 第 {self.current_chapter} 章 🔄 需修订\n\n{review}\n\n---\n\n原稿:\n{chapter_text}"

    @staticmethod
    def _parse_review_verdict(review: str) -> str:
        """从 review 文本首行提取 VERDICT，默认 REVISE（保守起见）。"""
        if not review:
            return "REVISE"
        for line in review.splitlines()[:5]:
            m = re.search(r'VERDICT\s*[:：]\s*(PASS|REVISE|REJECT)', line, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        # 兜底：若 LLM 没按格式输出，保守判定为需修订
        return "REVISE"

    @staticmethod
    def _parse_suggested_chapters(plan: str) -> int:
        """从企划书中提取"建议章节数"，找不到返回 0。"""
        if not plan:
            return 0
        # 匹配 "建议章节数: 12" / "建议章节数：12" / "章节数: 12" 等
        m = re.search(r'(?:建议)?章节数\s*[:：]\s*(\d{1,3})', plan)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 200:
                return n
        # 兜底：匹配 "共 X 章" / "X 章节"
        m = re.search(r'共?\s*(\d{1,3})\s*章', plan)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 200:
                return n
        return 0

    async def phase_writing_parallel(
        self, start_chapter: int, count: int
    ) -> str:
        """并行写作阶段: 多个 Scene Writer 同时写不同章节.

        Args:
            start_chapter: 起始章节号
            count: 要写的章节数（最多 scene_writers 数量）
        """
        self.phase = "writing"
        context = self.knowledge.build_context()
        outline = self.knowledge.load_outline()

        # Limit to available writers
        writer_count = min(count, len(self.scene_writers))
        chapter_nums = list(range(start_chapter, start_chapter + writer_count))

        # Build prompts for each chapter
        async def write_chapter(writer: SceneWriter, ch_num: int) -> tuple[int, str]:
            await self._rate_limit_pause()
            ch_outline = self._extract_chapter_outline(outline, ch_num)
            prompt = f"请撰写第 {ch_num} 章。\n\n## 大纲内容\n"
            if ch_outline:
                prompt += ch_outline
            else:
                prompt += f"第 {ch_num} 章（根据上下文自然推进）"
            text = await writer.think(prompt, context)
            return ch_num, text

        # Parallel write
        tasks = []
        for i, ch_num in enumerate(chapter_nums):
            tasks.append(write_chapter(self.scene_writers[i], ch_num))

        results = await asyncio.gather(*tasks)

        output_parts = []
        for ch_num, text in results:
            if not text or text.startswith("[LLM API error"):
                output_parts.append(f"## 第 {ch_num} 章 ❌ 写作失败\n{text}")
                continue
            self._log("scene_writer", f"Chapter {ch_num}: {text[:100]}...")
            self.knowledge.save_chapter(ch_num, text, "scene_writer")
            output_parts.append(f"## 第 {ch_num} 章 (初稿)\n{text}")

        return "\n\n---\n\n".join(output_parts)

    # ── Phase 5: 完稿 ──────────────────────────────────────────

    async def phase_complete(self, review_criteria: str = "") -> str:
        """完稿阶段: 终审 + 输出 + 清洗版 TXT + 内容简介 + 封面提示词.

        Args:
            review_criteria: 可选的项目专属评审标准（附加到终审 prompt），
                例如玉璧之战的"荡气回肠、突出战争残酷"等要求。不传则用通用评审。
        """
        self.phase = "complete"
        full_text = self.knowledge.get_all_chapters_text()
        context = self.knowledge.build_context()

        # Final edit pass
        await self._rate_limit_pause()
        final_edit = await self.editor.think(
            "请对整个作品做最后一轮全文润色。关注整体文风统一。\n\n" + full_text,
            context,
        )
        self._log("editor", "Final edit complete")

        # Final continuity
        await self._rate_limit_pause()
        final_cont = await self.continuity_keeper.think(
            "请对全文做最终连续性检查。\n\n" + final_edit[:5000],
            context,
        )
        self._log("continuity_keeper", final_cont)

        # Final approval — 可附加项目专属评审标准
        await self._rate_limit_pause()
        review_prompt = "请对整部作品进行终审，确认交付。\n\n"
        if review_criteria:
            review_prompt += f"## 评审标准\n{review_criteria}\n\n"
        review_prompt += f"## 作品正文（节选）\n{final_edit[:5000]}"
        final_review = await self.showrunner.think(review_prompt, context)
        self._log("showrunner", final_review)

        # Save final markdown (润色版，保留 markdown)
        out_dir = Path(self.cfg.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        project = self.project_name or "story"
        output_path = out_dir / f"{project}_final.md"
        output_path.write_text(final_edit, encoding="utf-8")

        # ── 新增交付物：清洗版 TXT + 内容简介 + 封面提示词 ──
        delivery = await self._finalize_delivery(full_text)

        summary = (
            f"## 终审\n{final_review}\n\n"
            f"## 输出\n- 润色版 MD: {output_path}\n"
            f"{delivery}"
        )
        return summary

    async def _finalize_delivery(self, full_text: str) -> str:
        """完稿末尾的三件交付物：清洗版 TXT、内容简介、封面提示词.

        任何一件失败都不阻断其他件，返回各件产出路径的 markdown 列表。
        """
        out_dir = Path(self.cfg.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        project = self.project_name or "story"
        lines: list[str] = []

        # 1. 收集所有章节 {num: content}
        chapter_nums = self.knowledge.list_chapters()
        chapters: dict[int, str] = {}
        for num in chapter_nums:
            content = self.knowledge.load_chapter(num)
            if content:
                chapters[num] = content

        # 2. 每章标题（根据内容生成）
        titles: dict[int, str] = {}
        if chapters:
            await self._rate_limit_pause()
            try:
                titles = await self._generate_chapter_titles(chapters)
            except Exception as e:
                logger.warning("生成章节标题失败，回退默认标题: %s", e)
                titles = {}

        # 3. 清洗版 .txt
        try:
            txt_content = self._build_clean_txt(titles, chapters)
            txt_path = out_dir / f"{project}_final.txt"
            txt_path.write_text(txt_content, encoding="utf-8")
            lines.append(f"- 清洗版 TXT: {txt_path}")
            self._log("delivery", f"TXT saved: {txt_path} ({len(txt_content)} chars)")
        except Exception as e:
            logger.warning("生成清洗版 TXT 失败: %s", e)
            lines.append(f"- 清洗版 TXT: ❌ 失败 ({e})")

        # 4. 内容简介（≤500 字）
        synopsis = ""
        try:
            await self._rate_limit_pause()
            synopsis = await self._generate_synopsis(full_text)
            synopsis_path = out_dir / f"{project}_synopsis.txt"
            synopsis_path.write_text(synopsis, encoding="utf-8")
            lines.append(f"- 内容简介: {synopsis_path}")
            self._log("delivery", f"Synopsis saved: {synopsis_path} ({len(synopsis)} chars)")
        except Exception as e:
            logger.warning("生成内容简介失败: %s", e)
            lines.append(f"- 内容简介: ❌ 失败 ({e})")

        # 5. 封面提示词 + dry-run
        try:
            await self._rate_limit_pause()
            brief_info = await self._generate_cover_brief(synopsis, full_text, out_dir, project)
            if brief_info:
                lines.append(f"- 封面 brief: {brief_info['brief']}")
                lines.append(f"- 封面提示词: {brief_info['prompt']}")
                # dry-run 调用封面工具生成 workflow JSON（不连 ComfyUI）
                wf = await self._render_cover_dry_run(brief_info["brief"], out_dir)
                if wf:
                    lines.append(f"- 封面 workflow: {wf}")
        except Exception as e:
            logger.warning("生成封面提示词失败: %s", e)
            lines.append(f"- 封面提示词: ❌ 失败 ({e})")

        return "\n".join(lines)

    async def _generate_chapter_titles(self, chapters: dict[int, str]) -> dict[int, str]:
        """调用 TitleDesigner 根据每章内容生成标题，返回 {章号: 标题}。

        解析 LLM 输出的 `第N章：[标题]` 行；解析失败的章号回退为 `第 N 章`。
        """
        if not chapters:
            return {}
        # 构造每章摘要（首段 + 长度），避免 prompt 过长
        chapter_summaries: list[str] = []
        for num in sorted(chapters):
            body = chapters[num]
            first_para = body.strip().split("\n\n")[0][:300]
            chapter_summaries.append(f"第 {num} 章（{len(body)} 字）：{first_para}")
        prompt = (
            "请为以下每一章设计一个 6-12 字的章节标题，根据章节内容提炼。\n\n"
            "## 输出格式（必须严格遵守）\n"
            "每行一个章节，格式为 `第N章：标题`，不要附加风格说明或其他内容。\n"
            "例如：\n"
            "第1章：废柴之名\n"
            "第2章：觉醒\n\n"
            "## 章节内容摘要\n"
            + "\n".join(chapter_summaries)
        )
        response = await self.title_designer.think(prompt, model=self.cfg.light_model)
        self._log("title_designer", f"Chapter titles: {response[:200]}")

        titles: dict[int, str] = {}
        for num in chapters:
            # 匹配 "第1章：标题" / "第 1 章：标题" / "第1章 标题"
            m = re.search(
                rf'第\s*{num}\s*章\s*[:：]?\s*(.+)',
                response,
            )
            if m:
                title = m.group(1).strip().rstrip("。.")
                # 去掉行尾可能的 "（风格：XXX）" 后缀
                title = re.sub(r'[（(].*$', '', title).strip()
                if title:
                    titles[num] = title
            if num not in titles:
                titles[num] = f"第 {num} 章"  # 兜底
        return titles

    def _build_clean_txt(self, titles: dict[int, str], chapters: dict[int, str]) -> str:
        """把所有章节拼成清洗版 .txt 文本（带扉页和每章标题）。

        Args:
            titles: {章号: 标题}，缺失的章号回退为 "第 N 章"。
            chapters: {章号: 原始 .md 正文}。
        """
        project = self.project_name or "story"
        # 扉页：书名 + 作者
        parts = [
            f"《{project}》",
            f"作者：{DEFAULT_AUTHOR}",
            "",
            "=" * 40,
            "",
        ]
        for num in sorted(chapters):
            body = chapters[num]
            # 剥离已有的 # H1 标题行（避免重复）
            existing_title, rest = strip_existing_title(body)
            # 清洗正文
            clean_body = clean_chapter_body(rest)
            # 章节标题：优先用生成标题，其次已有标题，最后回退
            title = titles.get(num) or existing_title or f"第 {num} 章"
            parts.append(f"第 {num} 章 {title}")
            parts.append("")
            parts.append(clean_body)
            parts.append("")
            parts.append("")  # 章间多一空行
        # 去掉末尾多余空行，保留单个换行结尾
        return "\n".join(parts).rstrip() + "\n"

    async def _generate_synopsis(self, full_text: str) -> str:
        """调用 Showrunner 生成不超过 500 字的内容简介。

        后处理：去 markdown 标记 + 硬截断到 500 字。
        """
        # 全文可能很长，截断到 8000 字避免超 token
        excerpt = full_text[:8000]
        prompt = (
            "请基于以下小说正文，撰写一段**不超过 500 字**的内容简介。\n\n"
            "## 要求\n"
            "1. 包含主角、核心冲突、故事走向\n"
            "2. 不剧透结局\n"
            "3. 纯文本，无 markdown 标记，无标题，无分点\n"
            "4. 直接输出简介正文，不要任何引导语\n\n"
            "## 作品正文（节选）\n" + excerpt
        )
        response = await self.showrunner.think(prompt, model=self.cfg.light_model)
        self._log("showrunner", f"Synopsis: {response[:200]}")
        # 去标记 + 截断
        synopsis = clean_chapter_body(response)
        # 去掉可能残留的换行（简介应是单段连续文本）
        synopsis = " ".join(synopsis.split())
        if len(synopsis) > 500:
            synopsis = _truncate_at_sentence(synopsis, 500)
        return synopsis

    async def _generate_cover_brief(
        self,
        synopsis: str,
        full_text: str,
        out_dir: Path,
        project: str,
    ) -> dict | None:
        """调用 Showrunner 扮演 Cover Designer，产出封面 brief JSON + 英文提示词.

        保存 cover_brief.json 和 cover_prompt.txt 到 {out_dir}/covers/。
        解析失败则用 book_cover_comfy 的启发式回退。
        Returns: {"brief": Path, "prompt": Path} 或 None。
        """
        covers_dir = out_dir / "covers"
        covers_dir.mkdir(parents=True, exist_ok=True)

        excerpt = full_text[:8000]
        prompt = (
            "你现在是封面设计师 (Cover Designer)。请基于以下小说正文和简介，"
            "为本书设计一个封面视觉方案，输出一个 JSON 对象。\n\n"
            "## 输出格式（必须严格遵守）\n"
            "只输出一个 JSON 对象，不要附加任何说明文字、不要 markdown 代码块标记。"
            "字段如下：\n"
            "{\n"
            f'  "title": "{project}",\n'  # 强制使用项目名
            '  "subtitle": "副标题或类型卖点，可为空字符串",\n'
            f'  "author": "{DEFAULT_AUTHOR}",\n'  # 强制作者署名
            '  "genre": "英文类型描述，例如 Chinese historical war fiction / social suspense thriller",\n'
            '  "mood": "英文情绪关键词，例如 solemn, epic, tragic, heroic",\n'
            '  "core_visual": "英文核心视觉，一个强意象，不要堆砌",\n'
            '  "composition": "portrait book cover, centered composition, title-safe empty space at top and bottom",\n'
            '  "palette": "英文色彩方案，例如 deep bronze, ink black, muted gold, dark red",\n'
            '  "positive_prompt": "完整的英文视觉提示词，以 \\"Book cover, premium novel cover artwork, \\" 开头，'
            '以 \\"no readable text, no fake letters, no watermark, no logo\\" 结尾"\n'
            "}\n\n"
            "## 约束\n"
            "- positive_prompt 必须是完整的英文句子，包含 genre、core_visual、mood、palette\n"
            "- 不要在 positive_prompt 里写中文或书名/作者名（标题和作者由 overlay 单独渲染）\n"
            "- core_visual 应是故事中最具代表性的一帧画面\n\n"
            f"## 内容简介\n{synopsis}\n\n"
            f"## 作品正文（节选）\n{excerpt}"
        )
        response = await self.showrunner.think(prompt, model=self.cfg.light_model)
        self._log("showrunner", f"Cover brief: {response[:200]}")

        # 解析 JSON（容错：提取首个 {...}）
        brief = self._parse_cover_brief_json(response, project, full_text)
        if brief is None:
            logger.warning("Cover brief JSON 解析失败，使用启发式回退")
            brief = self._heuristic_cover_brief(project, full_text)

        # 强制 author 和 title（LLM 可能返回别的值，必须用项目元数据覆盖）
        brief["author"] = DEFAULT_AUTHOR
        brief["title"] = project

        # 保存 brief JSON
        brief_path = covers_dir / "cover_brief.json"
        brief_path.write_text(
            json.dumps(brief, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 保存纯英文提示词
        prompt_text = brief.get("positive_prompt", "")
        prompt_path = covers_dir / "cover_prompt.txt"
        prompt_path.write_text(prompt_text, encoding="utf-8")

        return {"brief": brief_path, "prompt": prompt_path}

    @staticmethod
    def _parse_cover_brief_json(
        response: str, project: str, full_text: str
    ) -> dict | None:
        """从 LLM 响应中提取 cover brief JSON。失败返回 None。"""
        if not response or response.startswith("[LLM API error"):
            return None
        # 去掉可能的 ```json 代码块标记
        cleaned = re.sub(r'^```(?:json)?\s*', '', response.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'\s*```\s*$', '', cleaned).strip()
        # 提取首个 {...}
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not m:
            return None
        try:
            brief = json.loads(m.group(0))
            if not isinstance(brief, dict):
                return None
            return brief
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _heuristic_cover_brief(project: str, full_text: str) -> dict:
        """JSON 解析失败时的启发式回退：复用 book_cover_comfy 的类型推断。"""
        try:
            from tools.book_cover_comfy import infer_genre_and_mood, extract_core_visual
            genre, mood, palette, _ = infer_genre_and_mood(full_text)
            core_visual = extract_core_visual(full_text, genre)
        except Exception:
            genre, mood, palette, core_visual = (
                "contemporary Chinese literary fiction",
                "restrained, emotional, cinematic",
                "muted gray, warm amber, deep blue",
                "symbolic scene from the story, one lonely figure in a cinematic environment",
            )
        positive_prompt = (
            f"Book cover, premium novel cover artwork, {genre}, {core_visual}, "
            f"portrait book cover, centered composition, title-safe empty space at top and bottom, "
            f"{mood}, dramatic lighting, high detail, painterly realistic illustration, "
            f"professional publishing cover design, {palette}, "
            f"no readable text, no fake letters, no watermark, no logo"
        )
        return {
            "title": project,
            "subtitle": "",
            "author": DEFAULT_AUTHOR,
            "genre": genre,
            "mood": mood,
            "core_visual": core_visual,
            "composition": "portrait book cover, centered composition, title-safe empty space at top and bottom",
            "palette": palette,
            "positive_prompt": positive_prompt,
        }

    async def _render_cover_dry_run(
        self, brief_path: Path, out_dir: Path
    ) -> Path | None:
        """用 --dry-run 调用 book_cover_comfy.py 生成 workflow JSON（不连 ComfyUI）。

        失败只 log warning，不抛异常。返回 workflow JSON 路径或 None。
        只返回本次 dry-run 新产出的 workflow 文件，避免拾取目录里残留的旧文件。
        """
        covers_dir = out_dir / "covers"
        cmd = [
            sys.executable,
            str(_COVER_TOOL),
            "--brief", str(brief_path),
            "--output-dir", str(covers_dir),
            "--dry-run",
        ]
        # 记录调用前已有的 workflow 文件，调用后只从新增文件里挑
        existing = set(covers_dir.glob("*_workflow.json"))
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(Path(__file__).resolve().parent),
                text=True,
                capture_output=True,
                timeout=120,
            )
            if proc.returncode != 0:
                logger.warning(
                    "封面 dry-run 失败 (exit %d): %s",
                    proc.returncode, (proc.stderr or proc.stdout)[-500:],
                )
                return None
            # 优先返回本次新产出的 workflow；为空则回退到全目录最新（容错）
            new_files = list(set(covers_dir.glob("*_workflow.json")) - existing)
            candidates = new_files or list(covers_dir.glob("*_workflow.json"))
            if candidates:
                return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]
            return None
        except Exception as e:
            logger.warning("封面 dry-run 异常: %s", e)
            return None

    # ── 辅助方法 ───────────────────────────────────────────────

    async def chat_with_agent(self, agent_name: str, message: str) -> str:
        """直接与指定 Agent 对话."""
        agent = self.agents.get(agent_name)
        if not agent:
            return f"未知 Agent: {agent_name}，可用: {', '.join(self.agents.keys())}"
        context = self.knowledge.build_context()
        return await agent.think(message, context)

    async def _team_discussion(self, topic: str) -> str:
        """团队讨论: 多个 Agent 围绕一个话题发表意见."""
        responses = []
        for name in ["world_architect", "character_designer"]:
            agent = self.agents[name]
            resp = await agent.think(f"请针对以下问题给出你的专业意见。\n\n{topic}")
            responses.append(f"**【{agent.name}】**\n{resp[:1000]}")
        return "\n\n".join(responses)

    def _save_characters(self, text: str):
        """从输出文本中提取并保存角色档案.

        只有包含角色关键字（姓名/性格/外貌/背景/动机/特质等）的 ## 段落才视为角色档案，
        避免把"创作风格""世界观"等非角色章节误存为角色。
        """
        # 角色段落应至少包含以下关键字之一
        char_keywords = (
            "性格", "外貌", "背景", "动机", "特质", "身份", "年龄",
            "Core Traits", "核心特质", "人物", "角色", " protagonist",
        )
        # 排除这些常见非角色标题
        non_char_titles = (
            "世界观", "创作", "风格", "基调", "大纲", "主题", "设定",
            "world", "style", "outline", "theme",
        )

        sections = re.split(r'\n##\s+', text)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            # First line is the character name
            lines = section.split("\n")
            name = lines[0].strip().rstrip(":")
            if not name or len(name) >= 30 or name.startswith("```"):
                continue
            # 排除明显非角色标题
            if any(kw in name for kw in non_char_titles):
                continue
            # 必须包含至少一个角色关键字才保存
            if not any(kw in section for kw in char_keywords):
                continue
            self.knowledge.save_character(name, f"## {name}\n" + "\n".join(lines[1:]))

    def _extract_chapter_outline(self, outline: str, chapter_num: int) -> str:
        """从大纲中提取指定章节的内容.

        匹配 "第X章" / "## X." / "Chapter X" 三种标记，截取到下一个章节标记为止。
        注意: 章号用边界断言，避免 "第1章" 误匹配 "第11章"。
        """
        if not outline:
            return ""

        cn = self._num_to_cn(chapter_num)
        candidates = [
            rf'第\s*{chapter_num}\s*章',
            rf'##\s*{chapter_num}\s*[\.\、]',
            rf'Chapter\s*{chapter_num}\b',
            rf'第\s*{cn}\s*章',
        ]
        # 下一章节标记的统一正则（数字或中文数字），支持 "## 第N章" 形式
        next_pat = re.compile(
            r'\n(?:##\s*)?第\s*\d+\s*章'
            r'|\n##\s*\d+\s*[\.\、]'
            r'|\n##\s*第\s*[一二三四五六七八九十]+\s*章'
            r'|\nChapter\s*\d+\b'
            r'|\n第\s*[一二三四五六七八九十]+\s*章'
        )

        for pat in candidates:
            m = re.search(pat, outline)
            if not m:
                continue
            start = m.start()
            rest = outline[start:]
            nxt = next_pat.search(rest[1:])  # 跳过开头的本章节标记
            end = (1 + nxt.start()) if nxt else len(rest)
            return rest[:end].strip()[:1500]
        return ""

    @staticmethod
    def _num_to_cn(n: int) -> str:
        """阿拉伯数字(1-99)转中文数字。"""
        cn_nums = "零一二三四五六七八九"
        if n <= 0:
            return str(n)
        if n < 10:
            return cn_nums[n]
        if n < 20:
            return "十" + ("" if n == 10 else cn_nums[n - 10])
        tens, ones = divmod(n, 10)
        return cn_nums[tens] + "十" + ("" if ones == 0 else cn_nums[ones])

    def _log(self, agent: str, content: str):
        """记录对话日志."""
        self.conversation_log.append({
            "agent": agent,
            "content": content[:500],
            "time": datetime.now().isoformat(),
        })

    def get_status(self) -> dict:
        """获取当前状态."""
        chapters = self.knowledge.list_chapters()
        return {
            "project": self.project_name,
            "phase": self.phase,
            "chapters_written": len(chapters),
            "total_chapters": self.total_chapters,
            "world_docs": self.knowledge.list_world_docs(),
            "characters": self.knowledge.list_characters(),
            "conversation_entries": len(self.conversation_log),
            "agents": [a.to_dict() for a in self.agents.values()],
            "scene_writers": len(self.scene_writers),
            "current_chapter": self.current_chapter,
            "model": self.cfg.main_model,
            "light_model": self.cfg.light_model,
        }
