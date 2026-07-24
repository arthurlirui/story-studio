"""断电恢复：轮次级 checkpoint 续写功能测试。

覆盖：
- KnowledgeStore.save/load/clear_round_checkpoint：原子读写 + 清理
- _write_chapter_with_revisions 崩溃后续写：从 checkpoint.round 继续，而非整章重写
- 已交付章节的残留 checkpoint 被主动清理
- checkpoint 在章节交付后被清理
- run.log 人类可读日志写入

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 手动驱动。
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
    """按 system prompt 角色返回预设响应的假 client。

    支持 write_call_count 追踪 scene_writer 被调了几次（用于验证续写跳过轮次）。
    per_round_verdict 可按轮次返回不同 verdict（round 0 = REVISE, round 1 = PASS）。
    """

    def __init__(self, *, verdicts=("PASS",), chapter_text_tpl="第 X 章初稿 v{n}"):
        # verdicts[i] = 第 i 轮的 VERDICT；超出索引用最后一个
        self.verdicts = verdicts
        self.chapter_text_tpl = chapter_text_tpl
        self.write_calls = 0
        self.review_calls = 0

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        prompt = messages[-1]["content"] if messages else ""
        sys_lower = (system or "").lower()

        # scene_writer 写作（含重写 prompt）
        if "scene writer" in sys_lower or "编剧" in (system or ""):
            self.write_calls += 1
            return f"{self.chapter_text_tpl.format(n=self.write_calls)}\n\n陈风走在山道上……"

        # showrunner review
        if "showrunner" in sys_lower or "评审" in prompt:
            self.review_calls += 1
            idx = min(self.review_calls - 1, len(self.verdicts) - 1)
            verdict = self.verdicts[idx]
            return f"VERDICT: {verdict}\n\n评审意见。"

        if "editor" in sys_lower or "润色" in prompt:
            return f"润色稿：{prompt[:30]}"

        if "continuity" in sys_lower or "连续性" in prompt:
            return "连续性检查通过。"

        # literary_advisor（摘要）
        if "literary" in sys_lower or "摘要" in prompt:
            return "本章摘要：主角前行。"

        return "（_ScriptedLLM 兜底）"


def _build_orch(tmp_path: Path, *, verdicts=("PASS",), max_rounds=3):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        max_rounds=max_rounds,
    )
    client = _ScriptedLLM(verdicts=verdicts)
    orch = StoryOrchestrator(cfg, client=client)

    async def _no_pause():
        return None

    orch._rate_limit_pause = _no_pause
    orch.project_name = "测试续写"
    orch.knowledge.save_outline("## 第 1 章 起\n## 第 2 章 承\n")
    return orch, client


# ── 1. KnowledgeStore checkpoint 原子读写 ─────────────────────


def test_checkpoint_save_load_clear(tmp_path: Path):
    """save_round_checkpoint → load_round_checkpoint → clear_round_checkpoint 闭环。"""
    from agents.knowledge import KnowledgeStore
    ks = KnowledgeStore(base_dir=str(tmp_path / "knowledge"))

    # 初始无 checkpoint
    assert ks.load_round_checkpoint(1) is None

    # 写入 write 步骤 checkpoint
    ks.save_round_checkpoint(
        1, 0, "write",
        chapter_text="初稿内容", batch_id="batch_abc",
    )
    cp = ks.load_round_checkpoint(1)
    assert cp is not None
    assert cp["chapter"] == 1
    assert cp["round"] == 0
    assert cp["step"] == "write"
    assert cp["chapter_text"] == "初稿内容"
    assert cp["batch_id"] == "batch_abc"
    assert "ts" in cp

    # 覆盖写到 review 步骤
    ks.save_round_checkpoint(
        1, 0, "review",
        chapter_text="初稿", edited="润色稿", review="VERDICT: REVISE",
        verdict="REVISE",
    )
    cp2 = ks.load_round_checkpoint(1)
    assert cp2["step"] == "review"
    assert cp2["verdict"] == "REVISE"
    assert cp2["edited"] == "润色稿"

    # 清理
    ks.clear_round_checkpoint(1)
    assert ks.load_round_checkpoint(1) is None

    # 清理不存在的 checkpoint 不报错
    ks.clear_round_checkpoint(999)


def test_checkpoint_load_corrupt_returns_none(tmp_path: Path):
    """损坏的 checkpoint 文件 load 返回 None 而非抛异常。"""
    from agents.knowledge import KnowledgeStore
    ks = KnowledgeStore(base_dir=str(tmp_path / "knowledge"))
    cp_path = ks._chapter_checkpoint_state_path(1)
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    cp_path.write_text("not json {{{", encoding="utf-8")
    assert ks.load_round_checkpoint(1) is None


# ── 2. 章节交付后 checkpoint 被清理 ───────────────────────────


def test_checkpoint_cleared_on_pass(tmp_path: Path):
    """章节 PASS 交付后 checkpoint 应被清理。"""
    orch, client = _build_orch(tmp_path, verdicts=("PASS",), max_rounds=2)
    _run(orch.phase_writing(1))
    assert orch.knowledge.is_chapter_delivered(1)
    assert orch.knowledge.load_round_checkpoint(1) is None


def test_checkpoint_cleared_on_exhausted(tmp_path: Path):
    """章节修订耗尽交付后 checkpoint 应被清理。"""
    # 始终 REVISE，max_rounds=2 → 耗尽交付
    orch, client = _build_orch(
        tmp_path, verdicts=("REVISE", "REVISE"), max_rounds=2,
    )
    _run(orch.phase_writing(1))
    assert orch.knowledge.is_chapter_delivered(1)
    assert orch.knowledge.load_round_checkpoint(1) is None


# ── 3. 核心：断电续写从 checkpoint.round 继续 ─────────────────


def test_resume_from_review_checkpoint_continues_next_round(tmp_path: Path):
    """崩溃在 round 0 review 之后（verdict=REVISE）：恢复应从 round 1 续写，
    而非从 round 0 重写。

    验证：恢复运行后 scene_writer 被调用次数 = 1（只写 round 1），
    而非 2（round 0 + round 1 都重写）。

    注意：checkpoint 已保存 round 0 的 review 结果，恢复后 round 0 被跳过，
    所以恢复后的第一次 review 调用对应 round 1。verdicts[0]="PASS" → round 1 PASS。
    """
    orch, client = _build_orch(
        tmp_path, verdicts=("PASS",), max_rounds=3,
    )

    # 手动构造崩溃现场：round 0 review 完成，verdict=REVISE，但章节未交付
    orch.knowledge.save_round_checkpoint(
        1, 0, "review",
        chapter_text="第 X 章初稿 v1（崩溃前）",
        edited="润色稿 v1",
        review="VERDICT: REVISE\n\n需修订",
        verdict="REVISE",
    )
    # 确认未交付（无 summary）
    assert not orch.knowledge.is_chapter_delivered(1)

    # 恢复运行：应从 round 1 续写
    _run(orch.phase_writing(1))

    # 章节应已交付
    assert orch.knowledge.is_chapter_delivered(1)
    # scene_writer 只应被调用 1 次（round 1），round 0 被跳过
    assert client.write_calls == 1, (
        f"恢复后应只写 1 次（round 1 续写），got {client.write_calls}"
    )


def test_resume_from_write_checkpoint_rewrites_same_round(tmp_path: Path):
    """崩溃在 round 1 write 步骤（本轮未完成）：恢复应从 round 1 的 write
    重新开始，复用 round 0 的 review 意见进入 round 1 的 prompt。

    构造：checkpoint round=1 step=write，但 chapter_text 是 round 0 的产物。
    恢复后应从 round 1 重写。

    注意：round 0 被跳过（cp_step=write 非 review → resume_from_round=1，
    从 round 1 重写）。round 1 的 review 是恢复后第一次 review 调用 → verdicts[0]。
    """
    orch, client = _build_orch(
        tmp_path, verdicts=("PASS",), max_rounds=3,
    )

    # 构造 round 0 已完成 review（verdict=REVISE），round 1 的 write 中途崩溃
    orch.knowledge.save_round_checkpoint(
        1, 1, "write",
        chapter_text="",  # round 1 write 未完成，无产物
        edited="",
        review="VERDICT: REVISE\n\nround 0 评审意见",
        verdict="REVISE",
    )
    assert not orch.knowledge.is_chapter_delivered(1)

    _run(orch.phase_writing(1))

    assert orch.knowledge.is_chapter_delivered(1)
    # round 1 的 write 被重新执行 → scene_writer 调用 1 次
    assert client.write_calls == 1, (
        f"应从 round 1 重写 1 次, got {client.write_calls}"
    )


def test_no_checkpoint_starts_from_round_0(tmp_path: Path):
    """无 checkpoint 时正常从 round 0 开始（不回归）。"""
    orch, client = _build_orch(
        tmp_path, verdicts=("PASS",), max_rounds=2,
    )
    _run(orch.phase_writing(1))
    assert client.write_calls == 1
    assert orch.knowledge.is_chapter_delivered(1)


def test_delivered_chapter_residual_checkpoint_cleaned(tmp_path: Path):
    """章节已交付但残留 checkpoint（交付时清理失败）：恢复时应主动清理。"""
    from agents.knowledge import KnowledgeStore
    orch, client = _build_orch(tmp_path, verdicts=("PASS",), max_rounds=2)

    # 先正常交付第 1 章
    _run(orch.phase_writing(1))
    assert orch.knowledge.is_chapter_delivered(1)

    # 手动塞入残留 checkpoint
    orch.knowledge.save_round_checkpoint(1, 0, "review", verdict="REVISE")
    assert orch.knowledge.load_round_checkpoint(1) is not None

    # 再次写第 1 章：入口检测到已交付 + 残留 checkpoint → 清理
    # phase_writing(1) 会重新进入 _write_chapter_with_revisions（chapter 已交付
    # 但本测试验证清理逻辑触发，不关心是否重写）
    _run(orch.phase_writing(1))
    assert orch.knowledge.load_round_checkpoint(1) is None


# ── 4. run.log 人类可读日志 ────────────────────────────────────


def test_run_log_written(tmp_path: Path):
    """phase_writing 后 run.log 应有可读日志行。"""
    orch, client = _build_orch(tmp_path, verdicts=("PASS",), max_rounds=2)
    _run(orch.phase_writing(1))

    log_path = Path(orch.cfg.output_dir) / "run.log"
    assert log_path.exists(), "run.log 应被创建"
    content = log_path.read_text(encoding="utf-8")
    # 应包含阶段切换 + 章节通过记录
    assert "阶段切换" in content or "writing" in content
    assert "第 1 章" in content
    assert "✅" in content


# ── 5. 批次并行下 checkpoint 隔离 ─────────────────────────────


def test_batch_checkpoint_per_chapter_isolated(tmp_path: Path):
    """批次并行写作时每章 checkpoint 独立，交付后各自清理。"""
    from agents.knowledge import KnowledgeStore

    class _BatchLLM:
        def __init__(self):
            self.write_calls = 0

        async def chat(self, *, messages, model, temperature, max_tokens, system):
            prompt = messages[-1]["content"] if messages else ""
            sys_lower = (system or "").lower()
            if "协调简报" in prompt:
                return (
                    '{"1": {"entry_state": "a", "exit_state": "b", "must_reveal": [], '
                    '"must_not_reveal": [], "handoff": "x"}, '
                    '"2": {"entry_state": "b", "exit_state": "c", "must_reveal": [], '
                    '"must_not_reveal": [], "handoff": "y"}}'
                )
            if "跨章一致性" in prompt:
                return "VERDICT: PASS\n\n无冲突"
            if "scene writer" in sys_lower or "编剧" in (system or ""):
                self.write_calls += 1
                return f"初稿 v{self.write_calls}\n\n内容……"
            if "评审" in prompt:
                return "VERDICT: PASS\n\n通过"
            if "润色" in prompt:
                return "润色稿"
            if "连续性" in prompt or "continuity" in sys_lower:
                return "通过"
            if "摘要" in prompt or "literary" in sys_lower:
                return "摘要"
            return "兜底"

    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=2,
        max_rounds=1,
        batch_size=2,
        merge_gate_rounds=1,
    )
    client = _BatchLLM()
    orch = StoryOrchestrator(cfg, client=client)

    async def _no_pause():
        return None
    orch._rate_limit_pause = _no_pause
    orch.project_name = "批次测试"
    orch.knowledge.save_outline("## 第 1 章 起\n## 第 2 章 承\n")

    _run(orch.phase_writing_batch(1, 2))

    # 两章都交付
    assert orch.knowledge.is_chapter_delivered(1)
    assert orch.knowledge.is_chapter_delivered(2)
    # 两章的 checkpoint 都被清理
    assert orch.knowledge.load_round_checkpoint(1) is None
    assert orch.knowledge.load_round_checkpoint(2) is None
    # current_chapter 推进到 2（批次游标一致性修复）
    assert orch.current_chapter == 2
