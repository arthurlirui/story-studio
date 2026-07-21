"""phase_writing_batch 集成测试。

用 _ScriptedLLM 控制 agent 返回，验证：
- 并行批次能交付所有章节
- 单章异常被隔离，不影响其它章
- 融合门 PASS 时不触发重写
- 融合门 REVISE 时对冲突章触发定向重写
- worklog 记录 plan/write/edit/review/merge 等动作
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from config import StudioConfig
from orchestrator import StoryOrchestrator


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _ScriptedLLM:
    """按 system prompt 角色返回预设响应的假 client。

    通过 merge_verdict 控制融合门（continuity_keeper 跨章审查）的 VERDICT。
    """

    def __init__(self, *, per_chapter_verdict="PASS", merge_verdict="PASS",
                 plan_json: str | None = None):
        self.per_chapter_verdict = per_chapter_verdict
        self.merge_verdict = merge_verdict
        self.plan_json = plan_json or (
            '{"1": {"entry_state": "a", "exit_state": "b", "must_reveal": [], '
            '"must_not_reveal": [], "handoff": "x"}, '
            '"2": {"entry_state": "b", "exit_state": "c", "must_reveal": [], '
            '"must_not_reveal": [], "handoff": "y"}, '
            '"3": {"entry_state": "c", "exit_state": "d", "must_reveal": [], '
            '"must_not_reveal": [], "handoff": "z"}}'
        )
        self.scene_writer_calls = 0
        self.showrunner_calls = 0
        self.merge_calls = 0

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        prompt = messages[-1]["content"] if messages else ""
        sys_lower = (system or "").lower()

        # 批次简报生成（showrunner，prompt 含"协调简报"）
        if "showrunner" in sys_lower and "协调简报" in prompt:
            return self.plan_json

        # 融合门（continuity_keeper，prompt 含"跨章一致性"）
        if "continuity" in sys_lower and "跨章一致性" in prompt:
            self.merge_calls += 1
            if self.merge_verdict == "PASS":
                return "VERDICT: PASS\n\n无冲突"
            return (
                'VERDICT: REVISE\n\n```json\n'
                '{"conflicts": [{"chapters": [1], "issue": "测试冲突", "severity": "high"}]}\n'
                '```'
            )

        # 单章 scene_writer
        if "scene writer" in sys_lower or "编剧" in (system or ""):
            self.scene_writer_calls += 1
            return f"第 X 章初稿 v{self.scene_writer_calls}\n\n陈风走在山道上……"

        # 单章 showrunner review
        if "showrunner" in sys_lower or "评审" in prompt:
            self.showrunner_calls += 1
            return f"VERDICT: {self.per_chapter_verdict}\n\n评审意见。"

        if "editor" in sys_lower or "润色" in prompt:
            return f"润色稿：{prompt[:30]}"

        if "continuity" in sys_lower or "连续性" in prompt:
            return "连续性检查通过。"

        # literary_advisor（摘要）
        if "literary" in sys_lower or "摘要" in prompt:
            return "本章摘要：主角前行。"

        return "（_ScriptedLLM 兜底）"


def _build_orch(tmp_path: Path, *, per_chapter_verdict="PASS", merge_verdict="PASS",
                scene_writers=3, merge_gate_rounds=1):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=scene_writers,
        max_rounds=1,
        batch_size=3,
        merge_gate_rounds=merge_gate_rounds,
    )
    client = _ScriptedLLM(
        per_chapter_verdict=per_chapter_verdict, merge_verdict=merge_verdict
    )
    orch = StoryOrchestrator(cfg, client=client)

    async def _no_pause():
        return None

    orch._rate_limit_pause = _no_pause
    orch.project_name = "测试批次"
    orch.knowledge.save_outline("## 第 1 章 起\n## 第 2 章 承\n## 第 3 章 转\n")
    return orch, client


# ── Tests ─────────────────────────────────────────────────────


def test_batch_delivers_all_chapters(tmp_path: Path):
    """3 章并行批次：所有章都应落盘，融合门 PASS 不触发重写。"""
    orch, client = _build_orch(tmp_path, merge_verdict="PASS")
    result = _run(orch.phase_writing_batch(1, 3))

    chapters = orch.knowledge.list_chapters()
    assert chapters == [1, 2, 3]
    # 融合门应被调用 1 次（PASS 直接放行）
    assert client.merge_calls == 1
    # 3 章各调 1 次 scene_writer（max_rounds=1）
    assert client.scene_writer_calls == 3


def test_batch_worklog_records_all_actions(tmp_path: Path):
    """worklog 应记录 plan / write / edit / continuity / review / summary / merge。"""
    orch, _ = _build_orch(tmp_path, merge_verdict="PASS")
    _run(orch.phase_writing_batch(1, 2))

    entries = orch.worklog.read_recent(500)
    actions = {e["action"] for e in entries}
    assert "plan" in actions
    assert "write" in actions
    assert "edit" in actions
    assert "continuity" in actions
    assert "review" in actions
    assert "summary" in actions
    assert "merge" in actions
    # 所有条目应有 batch_id
    assert all(e.get("batch_id") for e in entries)


def test_batch_merge_gate_revise_triggers_rewrite(tmp_path: Path):
    """融合门 REVISE：冲突章（第 1 章）应被定向重写。"""
    orch, client = _build_orch(
        tmp_path, per_chapter_verdict="PASS", merge_verdict="REVISE",
        merge_gate_rounds=1,
    )
    result = _run(orch.phase_writing_batch(1, 3))

    # 融合门第 1 次 REVISE → 触发重写第 1 章 → 第 2 次融合门复查
    # 重写调用 phase_writing（串行单章），它会再调 1 次 scene_writer
    assert client.merge_calls >= 2
    # 第 1 章应被重写：scene_writer 总调用 = 3（初次）+ 1（重写）= 4
    assert client.scene_writer_calls == 4
    # 结果文本应包含重写标记
    assert "融合门重写" in result or "融合门" in result


def test_batch_single_chapter_exception_isolated(tmp_path: Path):
    """单章异常应被隔离，不影响其它章交付。"""

    class _BoomLLM(_ScriptedLLM):
        async def chat(self, *, messages, model, temperature, max_tokens, system):
            prompt = messages[-1]["content"] if messages else ""
            sys_lower = (system or "").lower()
            # 让第 2 章的 scene_writer 抛异常（按"请撰写第 2 章"前缀精确匹配，
            # 避免命中邻居简报里的"第 2 章"字样）
            if ("scene writer" in sys_lower or "编剧" in (system or "")) and "请撰写第 2 章" in prompt:
                raise RuntimeError("第 2 章写作崩溃")
            return await super().chat(
                messages=messages, model=model, temperature=temperature,
                max_tokens=max_tokens, system=system,
            )

    cfg = StudioConfig(
        backend="llm", llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=3, max_rounds=1, batch_size=3, merge_gate_rounds=1,
    )
    client = _BoomLLM(merge_verdict="PASS")
    orch = StoryOrchestrator(cfg, client=client)

    async def _no_pause():
        return None

    orch._rate_limit_pause = _no_pause
    orch.project_name = "测试异常隔离"
    orch.knowledge.save_outline("## 第 1 章\n## 第 2 章\n## 第 3 章\n")

    result = _run(orch.phase_writing_batch(1, 3))
    # 异常应被捕获并体现在结果中
    assert "并行写作异常" in result or "❌" in result
    # 其它两章仍应落盘（融合门 PASS，跳过异常章）
    chapters = orch.knowledge.list_chapters()
    # 至少第 1、3 章应存在（第 2 章可能因异常未落盘）
    assert 1 in chapters
    assert 3 in chapters


def test_batch_respects_scene_writers_limit(tmp_path: Path):
    """count 超过 scene_writers 数时应自动截断。"""
    orch, client = _build_orch(tmp_path, scene_writers=2, merge_verdict="PASS")
    _run(orch.phase_writing_batch(1, 5))
    # 只应有 2 章被写
    assert client.scene_writer_calls == 2
    chapters = orch.knowledge.list_chapters()
    assert chapters == [1, 2]
