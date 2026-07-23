"""BatchCoordinator — 批次协调器（智能体集群的调度大脑）.

负责并行写作的两件协调工作：
1. plan_batch: 写作前由 Showrunner 生成「批次简报」，给每章规划入口/出口状态、
   必须揭示的伏笔、禁止提前揭示的内容、相邻章交接点。并行章节之间相互能看到彼此
   的简报片段，从而避免情节撞车、伏笔重复或漏接。
2. merge_gate: 写作后由 ContinuityKeeper + Showrunner 做跨章一致性硬门审查，
   输出冲突列表，供 orchestrator 对冲突章触发定向重写。

设计原则：
- 容错优先：LLM 返回坏 JSON 时退化到空简报/空冲突，不阻塞主流程
- 简报持久化到 story/batch_briefs/<batch_id>.json 供事后审计
- 协调器自身无状态，所有上下文从 knowledge + 参数注入
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# 简报中每章章节大纲截断长度
_CH_OUTLINE_LIMIT = 1200
# 已完成章节摘要喂给协调器的总预算
_PRIOR_SUMMARY_BUDGET = 4000
# 融合门审查时每章正文截断长度
_GATE_CHAPTER_LIMIT = 3000


class BatchCoordinator:
    """批次协调器：生成批次简报 + 跑融合门。"""

    def __init__(self, showrunner, continuity_keeper, knowledge, cfg, worklog, job_id: str = ""):
        self.showrunner = showrunner
        self.continuity_keeper = continuity_keeper
        self.knowledge = knowledge
        self.cfg = cfg
        self.worklog = worklog
        self.job_id = job_id

    # ── Step A: 预协调简报 ─────────────────────────────────────

    async def plan_batch(self, start: int, count: int) -> tuple[str, dict[int, dict]]:
        """生成本批次各章的协调简报。

        Returns:
            (batch_id, brief) — brief 是 {chapter_num: {entry_state, exit_state,
            must_reveal, must_not_reveal, handoff}} 字典。解析失败则各章为空 dict。
        """
        batch_id = f"batch_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        outline = self.knowledge.load_outline()

        # 收集本批次各章的章节大纲
        ch_outlines: dict[int, str] = {}
        for ch in range(start, start + count):
            # 复用 orchestrator 的章节大纲提取逻辑（这里用一个轻量内联实现，
            # 避免循环依赖；orchestrator 调用时会传入更精确的 chapter_outline）
            ch_outlines[ch] = self._extract_chapter_outline_local(outline, ch)

        # 收集已完成章节的摘要（供简报知道"前面发生过什么"）
        prior_summaries = self._collect_prior_summaries(start)

        prompt = self._build_plan_prompt(start, count, ch_outlines, prior_summaries)

        t0 = time.time()
        try:
            raw = await self.showrunner.think(prompt)
        except Exception as e:
            logger.warning("plan_batch 调用失败，退化空简报: %s", e)
            await self.worklog.append(
                phase="writing", batch_id=batch_id, agent="showrunner",
                role="Showrunner", action="plan", model=getattr(self.showrunner, "model", ""),
                excerpt="", duration_ms=int((time.time() - t0) * 1000),
                error=str(e),
            )
            return batch_id, {ch: {} for ch in range(start, start + count)}

        duration_ms = int((time.time() - t0) * 1000)
        brief = self._parse_plan_json(raw, start, count)

        # 持久化简报
        try:
            self.knowledge.save_batch_brief(batch_id, {
                "start": start, "count": count, "brief": brief,
            })
        except Exception as e:
            logger.warning("保存批次简报失败: %s", e)

        await self.worklog.append(
            phase="writing", batch_id=batch_id, agent="showrunner",
            role="Showrunner", action="plan",
            model=getattr(self.showrunner, "model", ""),
            usage=getattr(self.showrunner, "last_usage", None) or {},
            excerpt=(raw or "")[:200], duration_ms=duration_ms,
        )
        return batch_id, brief

    def _build_plan_prompt(
        self, start: int, count: int,
        ch_outlines: dict[int, str], prior_summaries: str,
    ) -> str:
        chapters_block = ""
        for ch in range(start, start + count):
            chapters_block += (
                f"\n### 第 {ch} 章大纲\n{ch_outlines.get(ch, '（无明确大纲，根据上下文推进）')}\n"
            )
        return (
            f"请为本批次 {count} 个并行章节生成协调简报，确保各章情节不撞车、伏笔不重复、"
            f"人物状态在章间正确交接。\n\n"
            f"## 已完成章节摘要\n{prior_summaries or '（无前序章节，本批为首批）'}\n\n"
            f"## 本批次各章大纲{chapters_block}\n\n"
            f"## 输出格式（必须严格遵守）\n"
            f"输出一段 JSON，键为章节号（字符串形式），值为该章的协调简报对象：\n"
            f"```json\n"
            f"{{\n"
            f'  "{start}": {{\n'
            f'    "entry_state": "本章开始时主角的状态/位置/最近事件",\n'
            f'    "exit_state": "本章结束时主角的状态/位置，应与下一章入口衔接",\n'
            f'    "must_reveal": ["本章必须揭示或推进的关键信息/伏笔"],\n'
            f'    "must_not_reveal": ["本章禁止提前揭示的后续悬念"],\n'
            f'    "handoff": "交给下一章的接力点（情节/物件/疑问）"\n'
            f"  }},\n"
            f'  "{start + 1}": {{ ... }},\n'
            f"  ...\n"
            f"}}\n"
            f"```\n"
            f"只输出 JSON，不要额外解释。"
        )

    def _parse_plan_json(self, raw: str, start: int, count: int) -> dict[int, dict]:
        """解析 Showrunner 返回的批次简报 JSON。失败则返回各章空 dict。"""
        if not raw:
            return {ch: {} for ch in range(start, start + count)}
        data = self._parse_json_block(raw)
        if not isinstance(data, dict):
            logger.warning("plan_batch JSON 解析失败，退化空简报。原始: %s", raw[:200])
            return {ch: {} for ch in range(start, start + count)}
        brief: dict[int, dict] = {}
        for ch in range(start, start + count):
            entry = data.get(str(ch)) or data.get(ch)
            brief[ch] = entry if isinstance(entry, dict) else {}
        return brief

    # ── Step C: 融合门 ─────────────────────────────────────────

    async def merge_gate(self, chapters: list[int], batch_id: str = "") -> dict[int, list[str]]:
        """跨章一致性硬门审查。

        Returns:
            {chapter_num: [issue1, issue2, ...]} — 需重写的章及冲突原因。
            空字典表示全部通过。
        """
        if not chapters:
            return {}
        # 收集各章正文（截断）
        parts: list[str] = []
        for ch in chapters:
            text = self.knowledge.load_chapter(ch)
            summary = self.knowledge.load_chapter_summary(ch)
            parts.append(
                f"### 第 {ch} 章\n摘要：{summary or '（无摘要）'}\n正文节选：\n{text[:_GATE_CHAPTER_LIMIT]}"
            )
        block = "\n\n".join(parts)

        prompt = (
            f"请审查以下 {len(chapters)} 个并行写成章节的跨章一致性。\n"
            f"重点检查：人物状态/位置衔接、时间线连续性、伏笔不重复揭示、术语/设定统一、"
            f"相邻章出口/入口是否对得上。\n\n"
            f"## 输出格式（必须严格遵守）\n"
            f"第一行必须是 `VERDICT: PASS` 或 `VERDICT: REVISE`；之后空一行；"
            f"然后输出 JSON：\n"
            f"```json\n"
            f'{{"conflicts":[{{"chapters":[<章节号>, ...], "issue":"...", "severity":"high|med|low"}}]}}\n'
            f"```\n"
            f"PASS=无严重跨章冲突；REVISE=存在需重写的冲突。只列出 high/med 级冲突，low 级忽略。\n\n"
            f"## 各章摘要与正文节选\n{block}"
        )

        t0 = time.time()
        try:
            raw = await self.continuity_keeper.think(prompt)
        except Exception as e:
            logger.warning("merge_gate 调用失败，按无冲突放行: %s", e)
            await self.worklog.append(
                phase="writing", batch_id=batch_id, agent="continuity_keeper",
                role="Continuity Keeper", action="merge",
                model=getattr(self.continuity_keeper, "model", ""),
                excerpt="", duration_ms=int((time.time() - t0) * 1000), error=str(e),
            )
            return {}

        duration_ms = int((time.time() - t0) * 1000)
        verdict = self._parse_verdict(raw)
        conflicts: dict[int, list[str]] = {}
        if verdict == "PASS":
            await self.worklog.append(
                phase="writing", batch_id=batch_id, agent="continuity_keeper",
                role="Continuity Keeper", action="merge", verdict="PASS",
                model=getattr(self.continuity_keeper, "model", ""),
                usage=getattr(self.continuity_keeper, "last_usage", None) or {},
                excerpt=(raw or "")[:200], duration_ms=duration_ms,
            )
            return {}

        # 解析冲突列表
        data = self._parse_json_block(raw)
        if isinstance(data, dict) and isinstance(data.get("conflicts"), list):
            for c in data["conflicts"]:
                if not isinstance(c, dict):
                    continue
                issue = c.get("issue", "未命名冲突")
                for ch in c.get("chapters", []) or []:
                    try:
                        ch_int = int(ch)
                    except (TypeError, ValueError):
                        continue
                    conflicts.setdefault(ch_int, []).append(issue)

        await self.worklog.append(
            phase="writing", batch_id=batch_id, agent="continuity_keeper",
            role="Continuity Keeper", action="merge", verdict="REVISE",
            model=getattr(self.continuity_keeper, "model", ""),
            usage=getattr(self.continuity_keeper, "last_usage", None) or {},
            excerpt=(raw or "")[:200], duration_ms=duration_ms,
        )
        return conflicts

    # ── 辅助 ───────────────────────────────────────────────────

    def _collect_prior_summaries(self, start: int) -> str:
        """收集 start 之前已完成章节的摘要，总字符不超过 _PRIOR_SUMMARY_BUDGET。"""
        chapters = self.knowledge.list_chapters()
        prior = [ch for ch in chapters if ch < start]
        if not prior:
            return ""
        parts: list[str] = []
        total = 0
        for ch in prior[-20:]:  # 最近 20 章
            s = self.knowledge.load_chapter_summary(ch)
            if not s:
                continue
            if total + len(s) > _PRIOR_SUMMARY_BUDGET:
                break
            parts.append(f"第 {ch} 章：{s}")
            total += len(s)
        return "\n".join(parts)

    def _extract_chapter_outline_local(self, outline: str, chapter_num: int) -> str:
        """轻量章节大纲提取（与 orchestrator._extract_chapter_outline 同源但内联，
        避免循环依赖）。orchestrator 调用时会传入更精确的 chapter_outline 覆盖。
        """
        if not outline:
            return ""
        # 匹配 "第N章" / "## N." / "Chapter N" 等开头，截到下一章或末尾
        patterns = [
            rf'第\s*{chapter_num}\s*章[^\n]*\n',
            rf'^##\s*{chapter_num}[.:：\s]',
            rf'^Chapter\s*{chapter_num}\b',
        ]
        for pat in patterns:
            m = re.search(pat, outline, re.MULTILINE)
            if m:
                rest = outline[m.end():]
                # 截到下一个章节标题
                nxt = re.search(r'(?:第\s*\d+\s*章|^##\s*\d+|^Chapter\s*\d+)', rest, re.MULTILINE)
                body = rest[:nxt.start()] if nxt else rest
                return body.strip()[:_CH_OUTLINE_LIMIT]
        return ""

    @staticmethod
    def _parse_json_block(text: str) -> Any:
        """容错提取 JSON：优先 ```json ... ``` 代码块，否则尝试首个 { 到末尾。"""
        if not text:
            return None
        # 1. 代码块
        m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        candidate = m.group(1).strip() if m else None
        if candidate:
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                pass
        # 2. 裸 JSON：找第一个 { 或 [ 到最后一个 } 或 ]
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = text.find(open_ch)
            end = text.rfind(close_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except (json.JSONDecodeError, ValueError):
                    continue
        return None

    @staticmethod
    def _parse_verdict(text: str) -> str:
        """从首行提取 VERDICT，默认 REVISE（保守）。"""
        if not text:
            return "REVISE"
        for line in text.splitlines()[:5]:
            m = re.search(r'VERDICT\s*[:：]\s*(PASS|REVISE|REJECT)', line, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        return "REVISE"
