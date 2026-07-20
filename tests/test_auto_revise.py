"""集成测试：phase_writing 的自动修订循环。

用 FakeLLMClient 控制 Showrunner 的 VERDICT，验证：
- 第 1 轮 PASS → 只跑 1 轮，立即交付，scene_writer 只被调 1 次
- 第 2 轮 PASS → 跑 2 轮，scene_writer 被调 2 次，回灌评审意见重写
- 耗尽 max_rounds 轮仍非 PASS → 标 ⚠️ 警告但仍交付
- run_state.json 在 PASS 后被持久化
- chapter_NNN_review.json 记录每轮评审
"""
from __future__ import annotations

import asyncio
import json
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
    """按调用次数 + agent 角色返回预设响应的假 client。

    通过外部传入的 verdict_schedule 控制 Showrunner 第 N 轮返回什么 VERDICT。
    """

    def __init__(self, verdict_schedule: list[str]):
        # verdict_schedule[i] = 第 i 轮（0-indexed）Showrunner 应返回的 VERDICT
        self.verdict_schedule = verdict_schedule
        self.scene_writer_calls = 0
        self.showrunner_calls = 0
        self.last_scene_prompt = ""

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        prompt = messages[-1]["content"] if messages else ""
        # system prompt 用来区分 agent 角色
        sys_lower = (system or "").lower()

        if "scene writer" in sys_lower or "编剧" in (system or ""):
            self.scene_writer_calls += 1
            self.last_scene_prompt = prompt
            return f"第 X 章初稿 v{self.scene_writer_calls}\n\n陈风走在山道上……"

        if "showrunner" in sys_lower or "总编剧" in (system or "") or "评审" in prompt:
            self.showrunner_calls += 1
            round_idx = self.showrunner_calls - 1
            verdict = (
                self.verdict_schedule[round_idx]
                if round_idx < len(self.verdict_schedule)
                else "PASS"
            )
            return f"VERDICT: {verdict}\n\n评审意见：第 {round_idx + 1} 轮。"

        if "editor" in sys_lower or "润色" in prompt:
            return f"润色稿：{prompt[:50]}"

        if "continuity" in sys_lower or "连续性" in prompt:
            return "连续性检查通过。"

        return "（_ScriptedLLM 兜底）"


def _build_orch(tmp_path: Path, verdict_schedule: list[str], max_rounds: int = 3):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        max_rounds=max_rounds,
    )
    client = _ScriptedLLM(verdict_schedule)
    orch = StoryOrchestrator(cfg, client=client)

    async def _no_pause():
        return None

    orch._rate_limit_pause = _no_pause
    orch.project_name = "测试修订"
    # 预置大纲，让 _extract_chapter_outline 有内容可读
    orch.knowledge.save_outline("## 第 1 章 起\n\n主角登场。\n")
    return orch, client


# ── Tests ────────────────────────────────────────────────────


def test_pass_on_round_1_returns_immediately(tmp_path: Path):
    """第 1 轮就 PASS：scene_writer 只被调 1 次。"""
    orch, client = _build_orch(tmp_path, verdict_schedule=["PASS"])
    result = _run(orch.phase_writing(1))

    assert "✅ 通过" in result
    assert "1 轮" in result
    assert client.scene_writer_calls == 1
    assert client.showrunner_calls == 1


def test_pass_on_round_2_revises_then_passes(tmp_path: Path):
    """第 1 轮 REVISE，第 2 轮 PASS：scene_writer 被调 2 次。"""
    orch, client = _build_orch(tmp_path, verdict_schedule=["REVISE", "PASS"])
    result = _run(orch.phase_writing(1))

    assert "✅ 通过" in result
    assert "2 轮" in result
    assert client.scene_writer_calls == 2
    assert client.showrunner_calls == 2


def test_reject_treated_as_revise(tmp_path: Path):
    """REJECT 与 REVISE 一样回灌重写。"""
    orch, client = _build_orch(tmp_path, verdict_schedule=["REJECT", "PASS"])
    result = _run(orch.phase_writing(1))

    assert "✅ 通过" in result
    assert client.scene_writer_calls == 2


def test_exhausted_rounds_delivers_with_warning(tmp_path: Path):
    """max_rounds=2 都 REVISE：标 ⚠️ 警告但仍交付。"""
    orch, client = _build_orch(
        tmp_path, verdict_schedule=["REVISE", "REVISE"], max_rounds=2
    )
    result = _run(orch.phase_writing(1))

    assert "⚠️ 修订耗尽" in result
    assert "2 轮未 PASS" in result
    assert client.scene_writer_calls == 2
    assert client.showrunner_calls == 2
    # 交付版本应仍落盘
    chapters = orch.knowledge.list_chapters()
    assert 1 in chapters


def test_review_recorded_per_round(tmp_path: Path):
    """每轮评审都写入 chapter_NNN_review.json。"""
    orch, _ = _build_orch(tmp_path, verdict_schedule=["REVISE", "PASS"])
    _run(orch.phase_writing(1))

    reviews = orch.knowledge.load_chapter_reviews(1)
    assert len(reviews) == 2
    assert reviews[0]["verdict"] == "REVISE"
    assert reviews[1]["verdict"] == "PASS"
    assert "round" in reviews[0]


def test_run_state_persisted_after_pass(tmp_path: Path):
    """PASS 后 run_state.json 应被持久化，phase=writing。"""
    orch, _ = _build_orch(tmp_path, verdict_schedule=["PASS"])
    _run(orch.phase_writing(1))

    state_path = Path(orch.cfg.knowledge_dir) / "run_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["phase"] == "writing"
    assert state["current_chapter"] == 1


def test_revise_feedback_fed_back_to_writer(tmp_path: Path):
    """第 2 轮的 scene_prompt 应包含上一轮的评审意见。"""
    orch, client = _build_orch(tmp_path, verdict_schedule=["REVISE", "PASS"])
    _run(orch.phase_writing(1))

    # 第 2 次 scene_writer 调用的 prompt 应含 "评审意见" 和上一轮 review 文本
    # （_ScriptedLLM 只存最后一次 prompt，所以这里检查最后一次）
    assert "评审意见" in client.last_scene_prompt
    assert "VERDICT: REVISE" in client.last_scene_prompt
