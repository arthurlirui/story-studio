"""
🎭 编排器 (Orchestrator) — 多 Agent 协作工作流引擎

协调整个创作流程：策划→建立→大纲→写作→修订
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from config import StudioConfig, load_config
from agents import (
    OllamaClient, VolcengineClient, Showrunner, WorldArchitect, CharacterDesigner,
    SceneWriter, Editor, LiteraryAdvisor, ContinuityKeeper,
    KnowledgeStore,
)
from agents.ollama_client import client as ollama_client
from agents.volcengine_client import client as volcengine_client

logger = logging.getLogger(__name__)


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
        self.client = client or volcengine_client

        # Knowledge store
        self.knowledge = KnowledgeStore(self.cfg.knowledge_dir)

        # Create agents — all use Volcengine API
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
        # Multiple Scene Writers for parallel chapter writing
        self.scene_writers: list[SceneWriter] = []
        for i in range(self.cfg.scene_writers):
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
            self.client, model=self.cfg.light_model, temperature=0.7,
        )
        self.continuity_keeper = ContinuityKeeper(
            "连续性检查员", "Continuity Keeper", "一致性检查",
            self.client, model=self.cfg.main_model, temperature=0.4,
        )

        self.agents = {
            "showrunner": self.showrunner,
            "world_architect": self.world_architect,
            "character_designer": self.character_designer,
            "editor": self.editor,
            "literary_advisor": self.literary_advisor,
            "continuity_keeper": self.continuity_keeper,
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

    async def phase_outlining(self, total_chapters: int = 10) -> str:
        """大纲阶段: 生成章节大纲."""
        self.phase = "outlining"
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

        # Literary advisor review
        lit_advice = await self.literary_advisor.think(
            "请分析以下章节大纲，给出结构建议。\n\n" + outline,
            context,
        )
        self._log("literary_advisor", lit_advice)

        # Final outline
        final_outline = await self.showrunner.think(
            f"结合文学顾问的建议，输出最终版章节大纲。\n\n"
            f"初始大纲:\n{outline}\n\n"
            f"文学建议:\n{lit_advice}"
        )
        self._log("showrunner", final_outline)

        self.knowledge.save_outline(final_outline)
        return final_outline

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
        chapter_text = await writer.think(scene_prompt, context)
        self._log("scene_writer", f"Chapter {self.current_chapter}: {chapter_text[:100]}...")
        self.knowledge.save_chapter(self.current_chapter, chapter_text, "scene_writer")

        # Step 2: Editor polish
        edited = await self.editor.think(
            f"请润色第 {self.current_chapter} 章。保留所有内容, 只优化表达。\n\n" + chapter_text,
            context,
        )
        self._log("editor", edited[:200])
        self.knowledge.save_chapter(self.current_chapter, edited, "editor")

        # Step 3: Continuity check
        continuity = await self.continuity_keeper.think(
            f"请检查第 {self.current_chapter} 章的一致性。\n\n" + edited,
            context,
        )
        self._log("continuity_keeper", continuity)
        self.knowledge.save_continuity_log(continuity)

        # Step 4: Showrunner review
        review = await self.showrunner.think(
            f"请评审第 {self.current_chapter} 章。\n\n"
            f"## 编辑后版本\n{edited[:3000]}\n\n"
            f"## 连续性检查\n{continuity[:1000]}",
        )
        self._log("showrunner", f"Review Ch{self.current_chapter}: {review[:200]}")

        if "通过" in review or "✅" in review:
            return f"## 第 {self.current_chapter} 章 ✅ 通过\n\n{edited}"
        else:
            return f"## 第 {self.current_chapter} 章 🔄 需修订\n\n{review}\n\n---\n\n原稿:\n{chapter_text}"

    async def phase_writing_parallel(
        self, start_chapter: int, count: int
    ) -> str:
        """并行写作阶段: 多个 Scene Writer 同时写不同章节.

        Args:
            start_chapter: 起始章节号
            count: 要写的章节数（最多 scene_writers 数量）
        """
        import asyncio

        self.phase = "writing"
        context = self.knowledge.build_context()
        outline = self.knowledge.load_outline()

        # Limit to available writers
        writer_count = min(count, len(self.scene_writers))
        chapter_nums = list(range(start_chapter, start_chapter + writer_count))

        # Build prompts for each chapter
        async def write_chapter(writer: SceneWriter, ch_num: int) -> tuple[int, str]:
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
            self._log("scene_writer", f"Chapter {ch_num}: {text[:100]}...")
            self.knowledge.save_chapter(ch_num, text, "scene_writer")
            output_parts.append(f"## 第 {ch_num} 章 (初稿)\n{text}")

        return "\n\n---\n\n".join(output_parts)

    # ── Phase 5: 完稿 ──────────────────────────────────────────

    async def phase_complete(self) -> str:
        """完稿阶段: 终审 + 输出."""
        self.phase = "complete"
        full_text = self.knowledge.get_all_chapters_text()
        context = self.knowledge.build_context()

        # Final edit pass
        final_edit = await self.editor.think(
            "请对整个作品做最后一轮全文润色。关注整体文风统一。\n\n" + full_text,
            context,
        )
        self._log("editor", "Final edit complete")

        # Final continuity
        final_cont = await self.continuity_keeper.think(
            "请对全文做最终连续性检查。\n\n" + final_edit[:5000],
            context,
        )
        self._log("continuity_keeper", final_cont)

        # Final approval
        final_review = await self.showrunner.think(
            "请对整部作品进行终审，确认交付。\n\n" + final_edit[:3000],
            context,
        )
        self._log("showrunner", final_review)

        # Save final output
        output_path = Path(self.cfg.output_dir) / f"{self.project_name or 'story'}_final.md"
        output_path.write_text(final_edit, encoding="utf-8")

        return f"## 终审\n{final_review}\n\n## 输出\n已保存至: {output_path}"

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
        """从输出文本中提取并保存角色档案."""
        import re

        # Try to find character sections by markdown headers
        sections = re.split(r'\n##\s+', text)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            # First line is the character name
            lines = section.split("\n")
            name = lines[0].strip().rstrip(":")
            if name and len(name) < 30 and not name.startswith("```"):
                self.knowledge.save_character(name, f"## {name}\n" + "\n".join(lines[1:]))

    def _extract_chapter_outline(self, outline: str, chapter_num: int) -> str:
        """从大纲中提取指定章节的内容."""
        import re

        # Look for "第 X 章" or "Chapter X" patterns
        patterns = [
            rf'(?:第\s*{chapter_num}\s*章[^#]*)',
            rf'(?:##\s*{chapter_num}\.\s*[^#]*)',
            rf'(?:Chapter\s*{chapter_num}[^#]*)',
        ]
        for pat in patterns:
            m = re.search(pat, outline, re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(0).strip()[:800]
        return ""

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
