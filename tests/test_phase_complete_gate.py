"""集成测试：phase_complete 的硬质量门。

验证：
- 终审 PASS → 不插警告头，正常交付
- 终审耗尽 max_rounds 仍非 PASS → _final.md 头部插 ⚠️ 警告但仍交付
- 终审循环最多跑 max_rounds 轮（editor 调用次数 ≤ max_rounds）
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


class _GateLLM:
    """控制终审 VERDICT 的假 client。

    verdict_schedule[i] = 第 i 轮终审返回的 VERDICT。
    其余 agent（editor/continuity/title/synopsis/cover）返回固定内容。
    """

    def __init__(self, verdict_schedule: list[str]):
        self.verdict_schedule = verdict_schedule
        self.editor_calls = 0
        self.showrunner_review_calls = 0  # 只数终审调用（不含 chapter review）

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        prompt = messages[-1]["content"] if messages else ""
        sys_lower = (system or "").lower()

        # 终审（phase_complete 里的 showrunner 调用，prompt 以 "请对整部作品进行终审" 开头）
        # 用更精确的匹配，避免 _finalize_delivery 的 synopsis/cover 提示词里也带 "终审"（来自上一轮的 full_text 预填）
        if ("showrunner" in sys_lower) and prompt.startswith("请对整部作品进行终审"):
            self.showrunner_review_calls += 1
            round_idx = self.showrunner_review_calls - 1
            verdict = (
                self.verdict_schedule[round_idx]
                if round_idx < len(self.verdict_schedule)
                else "PASS"
            )
            return f"VERDICT: {verdict}\n\n终审意见：第 {round_idx + 1} 轮。"

        # Showrunner 其他调用（synopsis / cover brief / 章节标题等）
        if "showrunner" in sys_lower:
            if "内容简介" in prompt or "500 字" in prompt:
                return "这是一个测试故事的简介。"
            if "封面" in prompt and "JSON" in prompt:
                import json
                return json.dumps({
                    "title": "x", "subtitle": "x", "author": "x",
                    "genre": "x", "mood": "x", "core_visual": "x",
                    "composition": "x", "palette": "x", "positive_prompt": "x",
                }, ensure_ascii=False)
            if "章节标题" in prompt or "为以下每一章设计" in prompt:
                return "第1章：觉醒\n"
            return "（_GateLLM showrunner 兜底）"

        if "editor" in sys_lower:
            self.editor_calls += 1
            if "最后一轮全文润色" in prompt:
                return "# 第 1 章\n\n润色后的正文内容。"
            return "润色稿。"

        if "continuity" in sys_lower:
            return "连续性检查通过。"

        # 章节标题
        if "章节标题" in prompt or "为以下每一章设计" in prompt:
            return "第1章：觉醒\n"

        # 内容简介
        if "内容简介" in prompt or "500 字" in prompt:
            return "这是一个测试故事的简介。"

        # 封面 brief
        if "封面" in prompt and "JSON" in prompt:
            import json
            return json.dumps({
                "title": "x", "subtitle": "x", "author": "x",
                "genre": "x", "mood": "x", "core_visual": "x",
                "composition": "x", "palette": "x", "positive_prompt": "x",
            }, ensure_ascii=False)

        return "（_GateLLM 兜底）"


def _build_orch(tmp_path: Path, verdict_schedule: list[str], max_rounds: int = 3):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        max_rounds=max_rounds,
    )
    client = _GateLLM(verdict_schedule)
    orch = StoryOrchestrator(cfg, client=client)

    async def _no_pause():
        return None

    orch._rate_limit_pause = _no_pause
    orch.project_name = "终审测试"
    orch.knowledge.save_chapter(1, "# 第 1 章\n\n正文内容。", author="scene_writer")
    return orch, client


# ── Tests ────────────────────────────────────────────────────


def test_final_pass_no_warning_header(tmp_path: Path):
    """终审第 1 轮 PASS：_final.md 不含 ⚠️ 警告头。"""
    orch, client = _build_orch(tmp_path, verdict_schedule=["PASS"])
    _run(orch.phase_complete())

    out_dir = Path(orch.cfg.output_dir)
    md = (out_dir / "终审测试_final.md").read_text(encoding="utf-8")
    assert "⚠️" not in md
    assert "终审未通过" not in md
    assert client.showrunner_review_calls == 1


def test_final_exhausted_inserts_warning_header(tmp_path: Path):
    """max_rounds=2 都 REVISE：_final.md 头部插 ⚠️ 警告但仍交付。"""
    orch, client = _build_orch(
        tmp_path, verdict_schedule=["REVISE", "REVISE"], max_rounds=2
    )
    result = _run(orch.phase_complete())

    out_dir = Path(orch.cfg.output_dir)
    md = (out_dir / "终审测试_final.md").read_text(encoding="utf-8")
    assert md.startswith("> ⚠️ 终审未通过")
    assert "耗尽 2 轮" in md
    assert "VERDICT: REVISE" in md
    # 交付物仍存在
    assert (out_dir / "终审测试_final.md").exists()
    assert client.showrunner_review_calls == 2


def test_final_loop_caps_at_max_rounds(tmp_path: Path):
    """终审循环最多跑 max_rounds 次 editor 调用。"""
    orch, client = _build_orch(
        tmp_path, verdict_schedule=["REVISE", "REVISE", "REVISE"], max_rounds=3
    )
    _run(orch.phase_complete())
    # editor 在每轮终审循环里被调 1 次（final edit），最多 3 次
    assert client.editor_calls <= 3
    assert client.showrunner_review_calls == 3


def test_final_reject_treated_as_revise_loops(tmp_path: Path):
    """REJECT 也应循环重润色，不立即终止。"""
    orch, client = _build_orch(
        tmp_path, verdict_schedule=["REJECT", "PASS"], max_rounds=3
    )
    _run(orch.phase_complete())

    out_dir = Path(orch.cfg.output_dir)
    md = (out_dir / "终审测试_final.md").read_text(encoding="utf-8")
    # 第 2 轮 PASS → 不应有警告头
    assert "⚠️" not in md
    assert client.showrunner_review_calls == 2
