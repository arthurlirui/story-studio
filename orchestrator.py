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
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import StudioConfig, load_config
from agents import (
    Showrunner, WorldArchitect, CharacterDesigner,
    SceneWriter, Editor, LiteraryAdvisor, ContinuityKeeper,
    TitleDesigner, Hooker, ClimaxDesigner,
    KnowledgeStore,
    WorkLog, BatchCoordinator,
    TopicResearcher, Innovator,
    get_search_provider,
)
from agents.llm_client import client as llm_client
from agents.llm_client import LLM_ERROR_PREFIX
from agents.text_cleaner import clean_chapter_body, strip_existing_title
from orchestrator_state import (
    RunState,
    new_job_id,
    PHASE_IDLE,
    PHASE_RESEARCH,
    PHASE_INNOVATE,
    PHASE_PLANNING,
    PHASE_BUILDING,
    PHASE_OUTLINING,
    PHASE_WRITING,
    PHASE_COMPLETE,
)

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


# 中文数字 → 阿拉伯数字（支持 1-999，与 _num_to_cn 互逆）
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(s: str) -> int | None:
    """中文数字转 int。支持 '一'..'九百九十九'，以及纯阿拉伯数字。返回 None 表示无法解析。"""
    s = s.strip()
    if not s:
        return None
    # 纯阿拉伯数字
    if s.isdigit():
        return int(s)
    # 含「百」优先处理（避免被下面的「十」字型误匹配，如「百十」）
    if "百" in s:
        return _cn_to_int_with_bai(s)
    # 单字：一/十/...九
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    # "十X" = 10 + X
    if len(s) == 2 and s[0] == "十":
        return 10 + _CN_DIGITS.get(s[1], 0)
    # "X十" = X*10
    if len(s) == 2 and s[1] == "十":
        return _CN_DIGITS.get(s[0], 0) * 10
    # "X十Y" = X*10 + Y
    if len(s) == 3 and s[1] == "十":
        return _CN_DIGITS.get(s[0], 0) * 10 + _CN_DIGITS.get(s[2], 0)
    return None


def _cn_to_int_with_bai(s: str) -> int | None:
    """解析含「百」的中文数字（1-999）。结构：[X]百[零Y | Y十[Z] | Y]。"""
    bai_idx = s.find("百")
    head = s[:bai_idx]
    # 百位前的数字（缺省为 1，如「百」=100、「一百」=100）；显式「二」..「九」也允许
    if head:
        if head not in _CN_DIGITS or head == "十":
            return None
        hundreds = _CN_DIGITS[head]
    else:
        hundreds = 1
    tail = s[bai_idx + 1:]
    if not tail:
        return hundreds * 100
    # 余部可能以「零」开头（如「一百零一」），去掉零后再解析个位
    if tail.startswith("零"):
        tail = tail[1:]
        if len(tail) != 1 or tail not in _CN_DIGITS:
            return None
        return hundreds * 100 + _CN_DIGITS[tail]
    # 其余余部走通用解析（十/X十/十Y/X十Y 等）
    tail_val = _cn_to_int(tail)
    if tail_val is None or tail_val >= 100:
        return None
    return hundreds * 100 + tail_val


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

        # Knowledge store (two-tier: series + variant) + research KB
        self.knowledge = KnowledgeStore(
            self.cfg.knowledge_dir,
            self.cfg.series_knowledge_dir,
            self.cfg.series_research_dir,
        )

        # Create agents — all use LLM API
        # Per-agent 模型路由：agent_models 覆盖 role 默认值；缺键回退到 main/light
        self.showrunner = Showrunner(
            "总策划", "Showrunner", "主持创作流程, 分配任务, 评审产出",
            self.client, model=self._agent_model("showrunner", "main"), temperature=0.6,
        )
        self.world_architect = WorldArchitect(
            "世界观架构师", "World Architect", "构建世界观设定",
            self.client, model=self._agent_model("world_architect", "main"), temperature=0.8,
        )
        self.character_designer = CharacterDesigner(
            "角色设计师", "Character Designer", "创建角色档案",
            self.client, model=self._agent_model("character_designer", "main"), temperature=0.8,
        )
        # Multiple Scene Writers for parallel chapter writing (at least 1)
        self.scene_writers: list[SceneWriter] = []
        writer_count = max(1, self.cfg.scene_writers)
        for i in range(writer_count):
            sw = SceneWriter(
                f"场景编剧{i + 1}", "Scene Writer", f"核心写作 #{i + 1}",
                self.client, model=self._agent_model("scene_writer", "main"),
                temperature=0.9, max_tokens=8192,
            )
            self.scene_writers.append(sw)
        self.editor = Editor(
            "编辑", "Editor", "文字润色",
            self.client, model=self._agent_model("editor", "light"), temperature=0.5,
        )
        self.literary_advisor = LiteraryAdvisor(
            "文学顾问", "Literary Advisor", "文学技巧建议",
            self.client, model=self._agent_model("literary_advisor", "light"), temperature=0.7,
        )
        self.continuity_keeper = ContinuityKeeper(
            "连续性检查员", "Continuity Keeper", "一致性检查",
            self.client, model=self._agent_model("continuity_keeper", "light"), temperature=0.4,
        )
        # Specialist designers (网文标题/钩子/爽点)
        self.title_designer = TitleDesigner(
            "标题设计师", "Title Designer", "设计书名/章节标题",
            self.client, model=self._agent_model("title_designer", "light"), temperature=0.8,
        )
        self.hooker = Hooker(
            "钩子设计师", "Hooker", "设计章节钩子",
            self.client, model=self._agent_model("hooker", "light"), temperature=0.8,
        )
        self.climax_designer = ClimaxDesigner(
            "爽点设计师", "Climax Designer", "设计爽点与高潮",
            self.client, model=self._agent_model("climax_designer", "light"), temperature=0.8,
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
        self.phase: str = PHASE_IDLE
        self.current_chapter: int = 0
        self.total_chapters: int = 0
        self.conversation_log: list[dict] = []
        self._call_count: int = 0
        # RunState：持久化运行进度 + 成本聚合
        self.job_id: str = new_job_id()
        self.run_cost: dict[str, dict[str, int]] = {}
        self._progress_log: list[dict] = []  # 进度日志（断电恢复用，从 run_state.json 恢复）
        self._state_path: Path = Path(self.cfg.knowledge_dir) / "run_state.json"
        self._load_state_from_disk()

        # 智能体集群工作记录（JSONL append-only，按 job 隔离）
        self.worklog = WorkLog(
            Path(self.cfg.knowledge_dir) / "story" / "agent_worklog.jsonl",
            job_id=self.job_id,
        )
        # 批次协调器（并行写作的预协调简报 + 融合门）
        self.coordinator = BatchCoordinator(
            self.showrunner, self.continuity_keeper, self.knowledge,
            self.cfg, self.worklog, self.job_id,
        )

        # 网络搜索 provider（可插拔：doubao / bocha / mock）
        self.web_search = get_search_provider(self.cfg)
        # 热点研究员 + 创新亮点策划师（research / innovate 阶段）
        self.topic_researcher = TopicResearcher(
            "热点研究员", "Topic Researcher", "调研热点/重要事件/同类小说/创作手法",
            self.client, model=self._agent_model("topic_researcher", "light"),
            temperature=0.5, max_tokens=4096,
        )
        self.innovator = Innovator(
            "创新亮点策划师", "Innovator", "基于私有 KB 产出创新亮点清单",
            self.client, model=self._agent_model("innovator", "main"),
            temperature=0.9, max_tokens=4096,
        )
        self.agents["topic_researcher"] = self.topic_researcher
        self.agents["innovator"] = self.innovator

    # ── RunState 持久化 ────────────────────────────────────────

    def _load_state_from_disk(self) -> None:
        """从 run_state.json 恢复状态（若存在）。"""
        state = RunState.load(self._state_path)
        if state:
            state.merge_into_orchestrator(self)
            # 恢复进度日志（断电恢复审计用）
            if state.progress_log:
                self._progress_log = list(state.progress_log)
            logger.info(
                "从 run_state.json 恢复: job_id=%s phase=%s project=%s chapter=%d/%d",
                self.job_id, self.phase, self.project_name or "(none)",
                self.current_chapter, self.total_chapters,
            )

    def _save_state(self) -> None:
        """持久化当前运行状态到 run_state.json。"""
        state = RunState(
            job_id=self.job_id,
            project_name=self.project_name,
            phase=self.phase,
            current_chapter=self.current_chapter,
            total_chapters=self.total_chapters,
            cost=dict(self.run_cost),
            progress_log=list(self._progress_log),
        )
        try:
            state.save(self._state_path)
        except Exception as e:
            logger.warning("保存 run_state 失败: %s", e)

    def _append_progress(self, event: dict) -> None:
        """追加进度日志并持久化（断电恢复审计用）。"""
        self._progress_log.append({
            **event, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self._save_state()

    def _record_usage(self, agent: Any) -> None:
        """从 agent.last_usage 聚合到 run_cost + 持久化。"""
        usage = getattr(agent, "last_usage", None)
        if not usage:
            return
        model = getattr(agent, "model", "unknown")
        bucket = self.run_cost.setdefault(model, {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
        })
        bucket["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
        bucket["completion_tokens"] += int(usage.get("completion_tokens", 0))
        bucket["total_tokens"] += int(usage.get("total_tokens", 0))
        bucket["calls"] += 1

    def _set_phase(self, phase: str) -> None:
        """切换 phase 并持久化。"""
        self.phase = phase
        self._save_state()

    def _agent_model(self, role: str, tier: str = "main") -> str:
        """Per-agent 模型路由：agent_models[role] 优先，缺键回退 main/light_model。

        tier="main" → 回退 self.cfg.main_model；tier="light" → 回退 self.cfg.light_model。
        """
        override = self.cfg.agent_models.get(role)
        if override:
            return override
        return self.cfg.light_model if tier == "light" else self.cfg.main_model

    def _set_project_name(self, name: str) -> None:
        """设置 project_name 并持久化。"""
        if name and not self.project_name:
            self.project_name = name
            self._save_state()

    def _set_total_chapters(self, total: int) -> None:
        """设置 total_chapters 并持久化。"""
        if total > 0:
            self.total_chapters = total
            self._save_state()

    async def _rate_limit_pause(self):
        """在连续 API 调用之间插入延迟，避免触发限流."""
        self._call_count += 1
        if self._call_count > 1:
            await asyncio.sleep(3.0)  # 3s between calls

    # ── Phase 0a: 调研 ─────────────────────────────────────────

    async def phase_research(self, brief: str) -> str:
        """调研阶段: 调用 TopicResearcher 联网搜索并沉淀到私有 KB。

        产出：research/{hot_events,important_events,similar_novels,creation_techniques}.md
        失败不阻塞：搜索 provider 异常 / LLM 异常均落空字符串 + 警告日志。
        """
        self._set_phase(PHASE_RESEARCH)
        self._log("user", f"[research] brief: {brief}")
        logger.info("phase_research: 开始调研 (provider=%s)", self.web_search.name)

        t0 = time.time()
        # C4 修复：从 cfg 读 research_max_topics，默认 4
        from agents.topic_researcher import DEFAULT_TOPICS
        max_topics = int(getattr(self.cfg, "research_max_topics", 4) or 4)
        if max_topics < len(DEFAULT_TOPICS):
            topics = DEFAULT_TOPICS[:max_topics]
        elif max_topics > len(DEFAULT_TOPICS):
            logger.warning(
                "phase_research: research_max_topics=%d 超过 DEFAULT_TOPICS 数量 %d，"
                "仅使用前 %d 个", max_topics, len(DEFAULT_TOPICS), len(DEFAULT_TOPICS),
            )
            topics = DEFAULT_TOPICS
        else:
            topics = DEFAULT_TOPICS
        try:
            results = await self.topic_researcher.research(
                brief, self.web_search, self.knowledge,
                topics=topics,
                on_usage=self._record_usage,  # C2 修复：每次 think() 后累加 usage
            )
        except Exception as e:
            logger.exception("phase_research 异常: %s", e)
            await self.worklog.append(
                phase=PHASE_RESEARCH, agent=self.topic_researcher.name,
                role="topic_researcher", action="research",
                model=self.topic_researcher.model, error=str(e),
                duration_ms=int((time.time() - t0) * 1000),
            )
            return f"## 调研失败\n\n{e}"

        # C2 修复后：usage 已通过 on_usage 回调逐次累加，不再需要循环外再调一次
        # （重复调用会导致最后一次 think() 的 usage 被二次计入）

        # 汇总摘要
        summary_lines = []
        total_sources = 0
        for slug, meta in results.items():
            n_src = len(meta.get("sources", []))
            total_sources += n_src
            first_line = (meta.get("content") or "").strip().split("\n", 1)[0][:80]
            summary_lines.append(f"- **{slug}**: {n_src} 条来源 — {first_line}")
        summary = "## 调研完成\n\n" + "\n".join(summary_lines)
        summary += f"\n\n共检索 {len(results)} 个主题，{total_sources} 条来源。"

        await self.worklog.append(
            phase=PHASE_RESEARCH, agent=self.topic_researcher.name,
            role="topic_researcher", action="research",
            model=self.topic_researcher.model,
            excerpt=summary[:200],
            duration_ms=int((time.time() - t0) * 1000),
        )
        self._log("assistant", summary)
        return summary

    # ── Phase 0b: 创新亮点 ─────────────────────────────────────

    async def phase_innovate(self, brief: str = "") -> str:
        """创新亮点阶段: 基于私有 KB 产出 5-8 个创新亮点并落盘到 research/highlights.md。"""
        self._set_phase(PHASE_INNOVATE)
        self._log("user", f"[innovate] brief: {brief[:80]}")
        logger.info("phase_innovate: 产出创新亮点")

        t0 = time.time()
        try:
            highlights = await self.innovator.innovate(self.knowledge, brief)
        except Exception as e:
            logger.exception("phase_innovate 异常: %s", e)
            await self.worklog.append(
                phase=PHASE_INNOVATE, agent=self.innovator.name,
                role="innovator", action="innovate",
                model=self.innovator.model, error=str(e),
                duration_ms=int((time.time() - t0) * 1000),
            )
            return f"## 创新亮点生成失败\n\n{e}"

        self._record_usage(self.innovator)

        await self.worklog.append(
            phase=PHASE_INNOVATE, agent=self.innovator.name,
            role="innovator", action="innovate",
            model=self.innovator.model,
            excerpt=highlights[:200],
            duration_ms=int((time.time() - t0) * 1000),
        )
        self._log("assistant", highlights)
        return highlights

    # ── Phase 1: 策划 ──────────────────────────────────────────

    async def phase_planning(self, user_request: str) -> str:
        """策划阶段: 接收用户需求，生成创作企划."""
        # 幂等守卫：已有企划书则跳过（断电恢复不重跑已完成阶段）
        existing_plan = self.knowledge.load_world("plan")
        if existing_plan.strip():
            logger.info("恢复：企划书已存在，跳过 phase_planning")
            self._set_phase(PHASE_PLANNING)
            return existing_plan
        self._set_phase(PHASE_PLANNING)
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
        # 幂等守卫：已有世界观设定则跳过（断电恢复不重跑已完成阶段）
        existing_settings = self.knowledge.load_world("settings")
        if existing_settings.strip():
            logger.info("恢复：世界观设定已存在，跳过 phase_building")
            self._set_phase(PHASE_BUILDING)
            return existing_settings
        self._set_phase(PHASE_BUILDING)
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
        # 幂等守卫：已有大纲则跳过（断电恢复不重跑已完成阶段）
        existing_outline = self.knowledge.load_outline()
        if existing_outline.strip():
            logger.info("恢复：大纲已存在，跳过 phase_outlining")
            self._set_phase(PHASE_OUTLINING)
            # 仍尝试解析总章节数（后续写作阶段需要）
            if total_chapters is None:
                plan = self.knowledge.load_world("plan")
                total_chapters = self._parse_suggested_chapters(plan) or 10
            self.total_chapters = total_chapters
            return existing_outline
        self._set_phase(PHASE_OUTLINING)

        if total_chapters is None:
            plan = self.knowledge.load_world("plan")
            total_chapters = self._parse_suggested_chapters(plan) or 10
        self.total_chapters = total_chapters

        context = self.knowledge.build_context(max_chars=self.cfg.max_context_chars)

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
        if title:
            self._set_project_name(title)
            if title == self.project_name:
                logger.info("从大纲解析到书名: %s", title)

        # 从大纲中解析总章节数（若调用方未指定），持久化
        if not self.total_chapters:
            parsed_total = self._parse_total_chapters(final_outline)
            if parsed_total:
                self._set_total_chapters(parsed_total)
                logger.info("从大纲解析到总章节数: %d", parsed_total)

        self._save_state()
        return final_outline

    @staticmethod
    def _parse_total_chapters(outline: str) -> int | None:
        """从大纲文本中提取总章节数。返回整数或 None。

        优先匹配 "第N章" 序号的最大值；失败再匹配 "共N章" / "N章" 字样。
        """
        if not outline:
            return None
        # 1. 收集所有 "第N章" 的 N（支持中文数字）
        chapter_nums: list[int] = []
        for m in re.finditer(r'第\s*([一二三四五六七八九十百零\d]+)\s*章', outline):
            n = _cn_to_int(m.group(1))
            if n and n > 0:
                chapter_nums.append(n)
        if chapter_nums:
            return max(chapter_nums)
        # 2. "共N章" / "全书N章" / "N章" 字样
        m = re.search(r'(?:共|全书|总计)\s*(\d+)\s*章', outline)
        if m:
            return int(m.group(1))
        m = re.search(r'^\s*(\d+)\s*章\s*$', outline, re.MULTILINE)
        if m:
            return int(m.group(1))
        return None

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
        """写作阶段: 写一章 → 润色 → 检查 → 评审（带自动修订循环）.

        自动修订：若 Showrunner 给出 REVISE/REJECT，将评审意见回灌给 scene_writer
        重写，最多 self.cfg.max_rounds 轮。PASS 或耗尽轮次则交付（耗尽时标警告）。
        """
        self._set_phase(PHASE_WRITING)

        if chapter_num:
            self.current_chapter = chapter_num
        else:
            chapters = self.knowledge.list_chapters()
            self.current_chapter = (chapters[-1] if chapters else 0) + 1

        context = self.knowledge.build_context(self.current_chapter,
                                                max_chars=self.cfg.max_context_chars)
        outline = self.knowledge.load_outline()
        chapter_outline = self._extract_chapter_outline(outline, self.current_chapter)

        result = await self._write_chapter_with_revisions(
            writer=self.scene_writers[0],
            editor=self.editor,
            continuity_keeper=self.continuity_keeper,
            showrunner=self.showrunner,
            chapter_num=self.current_chapter,
            context=context,
            chapter_outline=chapter_outline,
            save_continuity=True,
            save_state_on_pass=True,
        )
        return result

    async def _write_chapter_with_revisions(
        self,
        *,
        writer: SceneWriter,
        editor: Editor,
        continuity_keeper: ContinuityKeeper,
        showrunner: Showrunner,
        chapter_num: int,
        context: str,
        chapter_outline: str,
        save_continuity: bool = True,
        save_state_on_pass: bool = True,
        batch_id: str | None = None,
        neighbor_briefs: str = "",
        chapter_brief: dict | None = None,
        literary_advisor: "LiteraryAdvisor | None" = None,
    ) -> str:
        """单章写作的完整修订流水线（串行/并行共享）。

        scene_writer → editor → continuity → showrunner review，含 max_rounds 修订循环。
        PASS 则交付并生成摘要；耗尽轮次则标警告交付。

        Args:
            writer/editor/continuity_keeper/showrunner: 注入的 agent 实例
                （并行批次传入每章专属实例，串行复用 self.*）。
            chapter_num: 要写的章节号。
            context: build_context 已组装好的上下文。
            chapter_outline: 本章大纲片段。
            save_continuity: 是否写 continuity_log.md（并行批次内跳过，避免并发覆盖）。
            save_state_on_pass: 是否在 PASS 时 _save_state（并行批次统一在批次末尾保存）。
            batch_id: 并行批次 ID（写工作记录用）。
            literary_advisor: 可选的专属文学顾问实例（并行批次传入每章独立实例，
                避免 _conversation_history 并发串扰；P1 修复）。None 时复用 self.literary_advisor。
            neighbor_briefs: 相邻章节的协调简报摘要（并行批次注入，串行为空）。
            chapter_brief: 本章协调简报 dict（并行批次注入，串行为 None）。
        """
        max_rounds = max(1, self.cfg.max_rounds)
        chapter_text = ""
        edited = ""
        review = ""
        verdict = "REVISE"

        # 协调简报前缀（若提供）
        brief_prefix = ""
        if chapter_brief or neighbor_briefs:
            brief_prefix = "## 批次协调简报\n"
            if chapter_brief:
                brief_prefix += (
                    f"### 本章（第 {chapter_num} 章）\n"
                    f"- 入口状态: {chapter_brief.get('entry_state', '（无）')}\n"
                    f"- 出口状态: {chapter_brief.get('exit_state', '（无）')}\n"
                    f"- 必须揭示: {chapter_brief.get('must_reveal', [])}\n"
                    f"- 禁止揭示: {chapter_brief.get('must_not_reveal', [])}\n"
                    f"- 交接点: {chapter_brief.get('handoff', '（无）')}\n"
                )
            if neighbor_briefs:
                brief_prefix += f"### 相邻章节简报\n{neighbor_briefs}\n"
            brief_prefix += "\n"

        for round_n in range(max_rounds):
            # Step 1: Write (第 0 轮用初稿 prompt；后续轮回灌评审意见)
            if round_n == 0:
                scene_prompt = (
                    f"请撰写第 {chapter_num} 章。\n\n"
                    f"{brief_prefix}"
                    f"## 大纲内容\n"
                )
                if chapter_outline:
                    scene_prompt += chapter_outline
                else:
                    scene_prompt += f"第 {chapter_num} 章（根据上下文自然推进）"
            else:
                scene_prompt = (
                    f"第 {chapter_num} 章上一稿评审未过（第 {round_n} 轮修订）。"
                    f"请根据评审意见重写本章。\n\n"
                    f"## 评审意见\n{review}\n\n"
                    f"## 上一稿\n{chapter_text}\n\n"
                    f"{brief_prefix}"
                    f"## 大纲内容\n{chapter_outline or '（根据上下文自然推进）'}"
                )

            t0 = time.time()
            await self._rate_limit_pause()
            chapter_text = await writer.think(scene_prompt, context)
            duration_ms = int((time.time() - t0) * 1000)
            self._record_usage(writer)
            if not chapter_text or chapter_text.startswith(LLM_ERROR_PREFIX):
                await self.worklog.append(
                    phase=PHASE_WRITING, chapter=chapter_num, batch_id=batch_id,
                    agent=writer.name, role=writer.role, action="write",
                    model=getattr(writer, "model", ""), round_n=round_n,
                    usage=getattr(writer, "last_usage", None) or {},
                    excerpt=(chapter_text or "")[:200], duration_ms=duration_ms,
                    error=(chapter_text or "")[:200] if chapter_text else "empty",
                )
                return f"## 第 {chapter_num} 章 ❌ 写作失败\n\n{chapter_text}"
            self._log("scene_writer", f"Chapter {chapter_num} round {round_n}: {chapter_text[:100]}...")
            await self.worklog.append(
                phase=PHASE_WRITING, chapter=chapter_num, batch_id=batch_id,
                agent=writer.name, role=writer.role, action="write",
                model=getattr(writer, "model", ""), round_n=round_n,
                usage=getattr(writer, "last_usage", None) or {},
                excerpt=chapter_text[:200], duration_ms=duration_ms,
            )

            # Step 2: Editor polish
            t0 = time.time()
            await self._rate_limit_pause()
            edited = await editor.think(
                f"请润色第 {chapter_num} 章。保留所有内容, 只优化表达。\n\n" + chapter_text,
                context,
            )
            duration_ms = int((time.time() - t0) * 1000)
            self._record_usage(editor)
            if not edited or edited.startswith(LLM_ERROR_PREFIX):
                edited = chapter_text  # 润色失败时退回原稿
            self._log("editor", edited[:200])
            self.knowledge.save_chapter(chapter_num, edited, "editor")
            await self.worklog.append(
                phase=PHASE_WRITING, chapter=chapter_num, batch_id=batch_id,
                agent=editor.name, role=editor.role, action="edit",
                model=getattr(editor, "model", ""), round_n=round_n,
                usage=getattr(editor, "last_usage", None) or {},
                excerpt=edited[:200], duration_ms=duration_ms,
            )

            # Step 3: Continuity check（守卫哨兵）
            t0 = time.time()
            await self._rate_limit_pause()
            continuity = await continuity_keeper.think(
                f"请检查第 {chapter_num} 章的一致性。\n\n" + edited,
                context,
            )
            duration_ms = int((time.time() - t0) * 1000)
            self._record_usage(continuity_keeper)
            self._log("continuity_keeper", continuity)
            if save_continuity and continuity and not continuity.startswith(LLM_ERROR_PREFIX):
                self.knowledge.save_continuity_log(continuity)
            await self.worklog.append(
                phase=PHASE_WRITING, chapter=chapter_num, batch_id=batch_id,
                agent=continuity_keeper.name, role=continuity_keeper.role,
                action="continuity", model=getattr(continuity_keeper, "model", ""),
                round_n=round_n,
                usage=getattr(continuity_keeper, "last_usage", None) or {},
                excerpt=(continuity or "")[:200], duration_ms=duration_ms,
            )

            # Step 4: Showrunner review — 要求首行输出结构化 VERDICT
            t0 = time.time()
            await self._rate_limit_pause()
            review = await showrunner.think(
                f"请评审第 {chapter_num} 章。\n\n"
                f"## 编辑后版本\n{edited[:3000]}\n\n"
                f"## 连续性检查\n{continuity[:1000]}\n\n"
                f"## 输出格式（必须严格遵守）\n"
                f"第一行必须是 `VERDICT: PASS` 或 `VERDICT: REVISE` 或 `VERDICT: REJECT`，"
                f"之后空一行再写评审意见。PASS=通过；REVISE=需修订；REJECT=严重偏离需重写。",
            )
            duration_ms = int((time.time() - t0) * 1000)
            self._record_usage(showrunner)
            self._log("showrunner", f"Review Ch{chapter_num} round {round_n}: {review[:200]}")

            verdict = self._parse_review_verdict(review)
            # 记录本轮评审（供事后审计）
            self.knowledge.save_chapter_review(chapter_num, round_n, verdict, review)
            await self.worklog.append(
                phase=PHASE_WRITING, chapter=chapter_num, batch_id=batch_id,
                agent=showrunner.name, role=showrunner.role, action="review",
                model=getattr(showrunner, "model", ""), round_n=round_n, verdict=verdict,
                usage=getattr(showrunner, "last_usage", None) or {},
                excerpt=(review or "")[:200], duration_ms=duration_ms,
            )

            if verdict == "PASS":
                self.knowledge.save_chapter(chapter_num, edited, "editor_pass")
                # 生成章节摘要（≤200 字）供后续章节 build_context 用，替代首段截断
                await self._generate_chapter_summary(
                    chapter_num, edited, batch_id=batch_id,
                    literary_advisor=literary_advisor,
                )
                rounds_desc = f"{round_n + 1} 轮" if round_n > 0 else "1 轮"
                # 断电恢复：无论串行/批次，章节交付后都持久化游标 + 记录进度日志。
                # 批次中途崩溃也能恢复到正确章节（原 save_state_on_pass 仅控制旧行为）。
                self._append_progress({
                    "phase": PHASE_WRITING, "chapter": chapter_num,
                    "batch_id": batch_id, "event": "chapter_passed",
                    "detail": f"{rounds_desc}通过",
                })
                if save_state_on_pass:
                    self._save_state()
                return f"## 第 {chapter_num} 章 ✅ 通过（{rounds_desc}）\n\n{edited}"
            # REVISE / REJECT：进入下一轮重写（REJECT 视为更严重的 REVISE）

        # 耗尽轮次仍非 PASS：交付 edited 但标警告
        self.knowledge.save_chapter(chapter_num, edited, "editor_revise_exhausted")
        # 耗尽轮次也生成摘要（交付版本仍有参考价值）
        await self._generate_chapter_summary(
            chapter_num, edited, batch_id=batch_id,
            literary_advisor=literary_advisor,
        )
        # 断电恢复：耗尽交付也记录进度日志 + 持久化游标
        self._append_progress({
            "phase": PHASE_WRITING, "chapter": chapter_num,
            "batch_id": batch_id, "event": "chapter_exhausted",
            "detail": f"{max_rounds} 轮未 PASS 仍交付",
        })
        if save_state_on_pass:
            self._save_state()
        return (
            f"## 第 {chapter_num} 章 ⚠️ 修订耗尽（{max_rounds} 轮未 PASS）\n\n"
            f"## 最终评审\n{review}\n\n---\n\n## 交付版本\n{edited}"
        )

    async def _generate_chapter_summary(
        self, chapter_num: int, chapter_text: str, *, batch_id: str | None = None,
        literary_advisor: "LiteraryAdvisor | None" = None,
    ) -> None:
        """用 literary_advisor（light_model）为章节生成 ≤200 字摘要并保存。

        失败不影响主流程（摘要缺失时 build_context 回退首段）。

        Args:
            literary_advisor: 可选的专属实例。并行批次下各章传入独立实例，
                避免共享 self.literary_advisor 的 _conversation_history 并发串扰
                及 last_usage 被兄弟协程覆盖（P1 修复）。None 时复用 self.literary_advisor（串行路径）。
        """
        advisor = literary_advisor or self.literary_advisor
        try:
            excerpt = chapter_text[:3000]
            prompt = (
                f"请为以下章节生成一段不超过 200 字的摘要，用于后续章节的上下文参考。\n"
                f"要求：纯文本，无标题，无 markdown，无引导语；聚焦关键情节、人物动作、状态变化。\n\n"
                f"## 第 {chapter_num} 章正文（节选）\n{excerpt}"
            )
            summary = await advisor.think(prompt)
            self._record_usage(advisor)
            # 截到 200 字以防 LLM 超长
            if summary and not summary.startswith(LLM_ERROR_PREFIX):
                self.knowledge.save_chapter_summary(chapter_num, summary[:200])
                self._log("literary_advisor", f"Summary Ch{chapter_num}: {summary[:80]}...")
                await self.worklog.append(
                    phase=PHASE_WRITING, chapter=chapter_num, batch_id=batch_id,
                    agent=advisor.name, role=advisor.role,
                    action="summary", model=getattr(advisor, "model", ""),
                    usage=getattr(advisor, "last_usage", None) or {},
                    excerpt=summary[:200],
                )
        except Exception as e:
            logger.warning("生成第 %d 章摘要失败: %s", chapter_num, e)

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

    async def phase_writing_batch(
        self, start_chapter: int, count: int
    ) -> str:
        """批次并行写作阶段：预协调简报 → 并行写作 → 后置融合门。

        三段式流程：
          A. BatchCoordinator.plan_batch 生成各章协调简报
          B. 多个 Scene Writer 并行写不同章节，每章跑完整修订流水线
             (scene → edit → continuity → review，含 max_rounds 修订循环)
          C. BatchCoordinator.merge_gate 跨章一致性硬门审查；
             冲突章触发定向重写 (phase_writing)，最多 merge_gate_rounds 轮

        Args:
            start_chapter: 起始章节号
            count: 要写的章节数（自动截断到 scene_writers 数量）
        """
        self._set_phase(PHASE_WRITING)
        outline = self.knowledge.load_outline()

        # 受可用编剧数约束
        writer_count = max(1, min(count, len(self.scene_writers)))
        chapter_nums = list(range(start_chapter, start_chapter + writer_count))

        # ── Step A: 预协调简报 ──────────────────────────────────
        batch_id, brief = await self.coordinator.plan_batch(start_chapter, writer_count)

        # ── Step B: 并行写作 ────────────────────────────────────
        # 每章任务构造专属 editor/continuity/showrunner 实例，避免共享
        # _conversation_history 在并发下串扰（agent 是轻量对象，只持 prompt + client ref）
        async def write_chapter_full(writer: SceneWriter, ch_num: int) -> tuple[int, str]:
            # 每章独立 build_context（排除当前章），避免共享 pre-batch snapshot
            context = self.knowledge.build_context(
                ch_num, max_chars=self.cfg.max_context_chars)
            ch_outline = self._extract_chapter_outline(outline, ch_num)

            # 相邻章简报摘要（前一章 + 后一章）
            neighbor_briefs = ""
            for nb_ch in (ch_num - 1, ch_num + 1):
                nb = brief.get(nb_ch)
                if nb:
                    neighbor_briefs += (
                        f"第 {nb_ch} 章: 入口={nb.get('entry_state', '？')}；"
                        f"出口={nb.get('exit_state', '？')}；"
                        f"交接={nb.get('handoff', '？')}\n"
                    )

            result = await self._write_chapter_with_revisions(
                writer=writer,
                editor=Editor(
                    "编辑", "Editor", "文字润色",
                    self.client, model=self._agent_model("editor", "light"),
                    temperature=0.5,
                ),
                continuity_keeper=ContinuityKeeper(
                    "连续性检查员", "Continuity Keeper", "一致性检查",
                    self.client, model=self._agent_model("continuity_keeper", "light"),
                    temperature=0.4,
                ),
                showrunner=Showrunner(
                    "总策划", "Showrunner", "主持创作流程, 分配任务, 评审产出",
                    self.client, model=self._agent_model("showrunner", "main"),
                    temperature=0.6,
                ),
                # P1 修复：每章独立 literary_advisor，避免并发 _conversation_history 串扰
                literary_advisor=LiteraryAdvisor(
                    "文学顾问", "Literary Advisor", "文学技巧建议",
                    self.client, model=self._agent_model("literary_advisor", "light"),
                    temperature=0.7,
                ),
                chapter_num=ch_num,
                context=context,
                chapter_outline=ch_outline,
                # 并行批次内不写 continuity_log（覆盖写会冲突），仅走 worklog；
                # 融合门后会写一次合并版
                save_continuity=False,
                save_state_on_pass=False,
                batch_id=batch_id,
                neighbor_briefs=neighbor_briefs,
                chapter_brief=brief.get(ch_num) or None,
            )
            return ch_num, result

        tasks = [
            write_chapter_full(self.scene_writers[i], ch_num)
            for i, ch_num in enumerate(chapter_nums)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        chapter_results: dict[int, str] = {}
        # 异常章节单独记录（key 用负数占位避免与正常章节号冲突）
        error_parts: list[str] = []
        for r in results:
            if isinstance(r, Exception):
                # 单章异常：log + 跳过，不影响其它章
                logger.exception("并行写作单章异常: %s", r)
                error_parts.append(f"## ❌ 并行写作异常\n{r}")
                continue
            ch_num, text = r
            chapter_results[ch_num] = text

        # 批次完成后统一保存一次状态
        if chapter_nums:
            self.current_chapter = max(chapter_nums)
            self._save_state()

        # ── Step C: 融合门（硬门）──────────────────────────────
        delivered = list(chapter_results.keys())
        # P1 修复：预初始化 output_parts，避免所有章都异常时（delivered 为空）
        # 下面 return 的 join(output_parts) 抛 NameError，丢失 error_parts 摘要。
        output_parts: list[str] = []
        if delivered:
            conflicts = await self.coordinator.merge_gate(delivered, batch_id=batch_id)
            if conflicts:
                gate_rounds = max(1, self.cfg.merge_gate_rounds)
                for gate_round in range(gate_rounds):
                    if not conflicts:
                        break
                    for ch_num, issues in conflicts.items():
                        # 定向重写：复用串行单章流程（已带 max_rounds 修订），
                        # build_context 此时能看到同批次其他章的最新摘要
                        logger.info("融合门重写第 %d 章（轮 %d）: %s",
                                    ch_num, gate_round + 1, issues)
                        rewrite_result = await self.phase_writing(ch_num)
                        chapter_results[ch_num] = rewrite_result + (
                            f"\n\n---\n\n## 🔁 融合门重写（轮 {gate_round + 1}）\n"
                            f"冲突原因: {'; '.join(issues)}"
                        )
                    # 再跑一次融合门看是否仍有冲突
                    conflicts = await self.coordinator.merge_gate(delivered, batch_id=batch_id)
                    if conflicts:
                        logger.warning("融合门第 %d 轮后仍有冲突: %s",
                                       gate_round + 1, list(conflicts.keys()))

                # 仍冲突的章标记警告并交付
                if conflicts:
                    for ch_num, issues in conflicts.items():
                        chapter_results[ch_num] = (
                            chapter_results.get(ch_num, "")
                            + f"\n\n## ⚠️ 融合门未通过\n冲突: {'; '.join(issues)}"
                        )

            # 重新组装输出（按章节号排序）+ 异常条目放最后
            output_parts = [chapter_results[ch] for ch in sorted(chapter_results)]

        # error_parts 无论是否有 delivered 章节都要附上（P1 修复：全失败时也返回错误摘要）
        output_parts.extend(error_parts)

        return "\n\n---\n\n".join(output_parts)

    # ── Phase 5: 完稿 ──────────────────────────────────────────

    async def phase_complete(self, review_criteria: str = "") -> str:
        """完稿阶段: 终审 + 输出 + 清洗版 TXT + 内容简介 + 封面提示词.

        Args:
            review_criteria: 可选的项目专属评审标准（附加到终审 prompt），
                例如玉璧之战的"荡气回肠、突出战争残酷"等要求。不传则用通用评审。

        终审硬门：若 Showrunner 终审非 PASS，重跑 final_edit 最多 max_rounds 次；
        仍非 PASS 则在 _final.md 头部插警告但仍交付（不卡死流程）。
        """
        self._set_phase(PHASE_COMPLETE)
        full_text = self.knowledge.get_all_chapters_text()
        context = self.knowledge.build_context(max_chars=self.cfg.max_context_chars)

        max_rounds = max(1, self.cfg.max_rounds)
        final_edit = full_text
        final_review = ""
        final_verdict = "REVISE"
        rounds_taken = 0
        # P1 修复：评审意见不污染 full_text（原代码把评审意见拼进 full_text，
        # 导致 _finalize_delivery 拿到的是"评审意见+正文"而非纯正文，生成的
        # 简介/封面 brief 基于错误文本）。用 edit_base_text 承载带意见的编辑输入。
        edit_base_text = full_text

        try:
            for round_n in range(max_rounds):
                rounds_taken = round_n + 1
                # Final edit pass
                await self._rate_limit_pause()
                final_edit = await self.editor.think(
                    "请对整个作品做最后一轮全文润色。关注整体文风统一。\n\n" + edit_base_text,
                    context,
                )
                self._record_usage(self.editor)
                if not final_edit or final_edit.startswith(LLM_ERROR_PREFIX):
                    final_edit = full_text  # 润色失败退回原稿
                self._log("editor", f"Final edit complete (round {round_n})")

                # Final continuity
                await self._rate_limit_pause()
                final_cont = await self.continuity_keeper.think(
                    "请对全文做最终连续性检查。\n\n" + final_edit[:5000],
                    context,
                )
                self._record_usage(self.continuity_keeper)
                self._log("continuity_keeper", final_cont)

                # Final approval — 可附加项目专属评审标准
                await self._rate_limit_pause()
                review_prompt = (
                    "请对整部作品进行终审，确认交付。\n\n"
                    "## 输出格式（必须严格遵守）\n"
                    "第一行必须是 `VERDICT: PASS` 或 `VERDICT: REVISE` 或 `VERDICT: REJECT`，"
                    "之后空一行再写评审意见。\n\n"
                )
                if review_criteria:
                    review_prompt += f"## 评审标准\n{review_criteria}\n\n"
                review_prompt += f"## 作品正文（节选）\n{final_edit[:5000]}"
                final_review = await self.showrunner.think(review_prompt, context)
                self._record_usage(self.showrunner)
                self._log("showrunner", f"Final review (round {round_n}): {final_review[:200]}")

                final_verdict = self._parse_review_verdict(final_review)
                if final_verdict == "PASS":
                    break
                # 非 PASS：若有下一轮，把评审意见带入下一轮 editor 的输入
                if round_n < max_rounds - 1:
                    edit_base_text = (
                        f"上一轮终审未过（{final_verdict}），评审意见：\n{final_review}\n\n"
                        f"---\n\n请基于以上意见重润色：\n\n{full_text}"
                    )

            # Save final markdown (润色版，保留 markdown)
            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            project = self.project_name or "story"
            output_path = out_dir / f"{project}_final.md"

            if final_verdict != "PASS":
                # 耗尽轮次仍非 PASS：头部插警告但仍交付
                warning = (
                    f"> ⚠️ 终审未通过（耗尽 {rounds_taken} 轮，最终 VERDICT: {final_verdict}）\n"
                    f"> {final_review[:300]}\n\n---\n\n"
                )
                output_path.write_text(warning + final_edit, encoding="utf-8")
            else:
                output_path.write_text(final_edit, encoding="utf-8")

            self._save_state()

            # ── 新增交付物：清洗版 TXT + 内容简介 + 封面提示词 ──
            delivery = await self._finalize_delivery(full_text)

            verdict_emoji = "✅" if final_verdict == "PASS" else "⚠️"
            summary = (
                f"## 终审 {verdict_emoji}（{rounds_taken} 轮，VERDICT: {final_verdict}）\n{final_review}\n\n"
                f"## 输出\n- 润色版 MD: {output_path}\n"
                f"{delivery}"
            )
            return summary
        finally:
            # P1 修复：无论 phase_complete 成功或异常都关闭连接池，避免泄漏。
            # 注意：jobs._run_job 的 finally 也会调 client.aclose（幂等，有 is_closed 守卫）。
            if hasattr(self.client, "aclose"):
                try:
                    await self.client.aclose()
                except Exception as e:
                    logger.warning("关闭 LLM 连接池失败: %s", e)
            if hasattr(self.web_search, "aclose"):
                try:
                    await self.web_search.aclose()
                except Exception as e:
                    logger.warning("关闭 web_search 连接池失败: %s", e)

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
        response = await self.title_designer.think(prompt)
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
        if not response or response.startswith(LLM_ERROR_PREFIX):
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
        context = self.knowledge.build_context(max_chars=self.cfg.max_context_chars)
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
        """阿拉伯数字(1-999)转中文数字。"""
        cn_nums = "零一二三四五六七八九"
        if n <= 0:
            return str(n)
        if n < 10:
            return cn_nums[n]
        if n < 20:
            return "十" + ("" if n == 10 else cn_nums[n - 10])
        if n < 100:
            tens, ones = divmod(n, 10)
            return cn_nums[tens] + "十" + ("" if ones == 0 else cn_nums[ones])
        if n < 1000:
            hundreds, rest = divmod(n, 100)
            # 始终输出百位系数（含「一」），保持与 _cn_to_int 互逆且无歧义
            head = cn_nums[hundreds] + "百"
            if rest == 0:
                return head
            if rest < 10:
                return head + "零" + cn_nums[rest]
            # 10-99 余部用递归
            return head + StoryOrchestrator._num_to_cn(rest)
        return str(n)

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
            "cost": self._cost_summary(),
        }

    def _cost_summary(self) -> dict:
        """返回可读的累计成本摘要。"""
        by_model = dict(self.run_cost)
        total_calls = sum(b.get("calls", 0) for b in by_model.values())
        total_tokens = sum(b.get("total_tokens", 0) for b in by_model.values())
        return {
            "by_model": by_model,
            "total_calls": total_calls,
            "total_tokens": total_tokens,
        }

    def _infer_phase_from_disk(self) -> str:
        """从盘上现有产物推断当前 phase。

        /next 在 phase=="idle" 但 run_state 缺失/陈旧时调用，让用户能从已有
        产物继续，而不是被卡在 "未创建项目" 提示里。
        推断顺序（从后往前）：有 final.md → complete；有章节 → writing；
        有 outline → outlining；有 world/character → building；否则 idle。
        新增 research/innovate 推断：有 world 产物但无 highlights → innovate；
        有 highlights 但无 world → planning；有 research 但无 highlights → innovate。
        """
        if (self.knowledge.story_dir / "final.md").exists():
            return PHASE_COMPLETE
        if self.knowledge.list_chapters():
            return PHASE_WRITING
        if self.knowledge.load_outline().strip():
            return PHASE_OUTLINING
        has_world = bool(self.knowledge.list_world_docs() or self.knowledge.list_characters())
        if has_world:
            return PHASE_BUILDING
        # research / innovate 推断（仅当完全没有 world 产物时才考虑）
        research_topics = set(self.knowledge.list_research_topics())
        has_highlights = "highlights" in research_topics
        has_research = bool(research_topics - {"highlights"})
        if has_research and not has_highlights:
            return PHASE_INNOVATE
        if has_highlights:
            return PHASE_PLANNING
        return PHASE_IDLE
