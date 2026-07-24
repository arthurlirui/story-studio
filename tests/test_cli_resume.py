"""CLI 断电恢复检测 + /resume + /discard 测试。

覆盖：
- _detect_resumable_run：识别未完成运行 / 排除已完成 / 排除从未开始
- /resume 命令：从 task_plan.json 断点继续
- /discard 命令：归档 state/plan 到 archive/
- 启动提示打印

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 手动驱动。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import StudioConfig
from orchestrator_state import (
    PHASE_WRITING, PHASE_RESEARCH, PHASE_IDLE, PHASE_COMPLETE, RunState,
)
from planner import Task, TaskPlan, TASK_PENDING, TASK_DONE, TASK_RUNNING


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _cfg(tmp_path: Path) -> StudioConfig:
    return StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        main_model="test-main",
        light_model="test-light",
        max_rounds=1,
    )


def _make_orch(tmp_path: Path):
    """构造一个不连真实 LLM 的 orchestrator（client 是 MagicMock）。"""
    from orchestrator import StoryOrchestrator
    cfg = _cfg(tmp_path)
    client = MagicMock()
    # agent.think 走 client.chat；mock 掉避免真实调用
    async def _fake_chat(**kw):
        return "（mock）"
    client.chat = _fake_chat
    orch = StoryOrchestrator(cfg, client=client)
    return orch


# ── 1. _detect_resumable_run ─────────────────────────────────


def test_detect_resumable_run_returns_info(tmp_path: Path):
    """有 run_state + task_plan 且有 pending 任务 → 返回描述 dict。"""
    orch = _make_orch(tmp_path)
    # 构造未完成运行
    state = RunState(
        job_id="j1", project_name="剑客", phase=PHASE_WRITING,
        current_chapter=3, total_chapters=10,
    )
    state.save(Path(orch.cfg.knowledge_dir) / "run_state.json")
    plan = TaskPlan(
        job_id="j1", brief="剑客", total_chapters=10,
        tasks=[
            Task(id=1, name="调研", phase=PHASE_RESEARCH, status=TASK_DONE),
            Task(id=2, name="写作", phase=PHASE_WRITING, status=TASK_PENDING),
            Task(id=3, name="完稿", phase=PHASE_COMPLETE, status=TASK_PENDING),
        ],
    )
    plan.save(Path(orch.cfg.knowledge_dir) / "task_plan.json")

    # 重新构造 orchestrator 让它从盘上加载状态
    orch2 = _make_orch(tmp_path)
    from main import _detect_resumable_run
    info = _detect_resumable_run(orch2)

    assert info is not None
    assert info["phase"] == PHASE_WRITING
    assert info["project_name"] == "剑客"
    assert info["current_chapter"] == 3
    assert info["total_chapters"] == 10
    assert info["pending_tasks"] == 2


def test_detect_resumable_run_skips_completed(tmp_path: Path):
    """所有任务 done + phase=complete → 不可恢复，返回 None。"""
    orch = _make_orch(tmp_path)
    state = RunState(
        job_id="j1", project_name="剑客", phase=PHASE_COMPLETE,
        current_chapter=10, total_chapters=10,
    )
    state.save(Path(orch.cfg.knowledge_dir) / "run_state.json")
    plan = TaskPlan(
        job_id="j1", brief="剑客", total_chapters=10,
        tasks=[
            Task(id=1, name="完稿", phase=PHASE_COMPLETE, status=TASK_DONE),
        ],
    )
    plan.save(Path(orch.cfg.knowledge_dir) / "task_plan.json")

    orch2 = _make_orch(tmp_path)
    from main import _detect_resumable_run
    assert _detect_resumable_run(orch2) is None


def test_detect_resumable_run_skips_never_started(tmp_path: Path):
    """phase=idle 且无 task_plan → 从未开始，返回 None。"""
    orch = _make_orch(tmp_path)
    from main import _detect_resumable_run
    # 无 run_state.json 也无 task_plan.json
    assert _detect_resumable_run(orch) is None


def test_detect_resumable_run_with_stale_running(tmp_path: Path):
    """崩溃中 running 任务被 load_plan 重置为 pending → 计入 pending_tasks。"""
    orch = _make_orch(tmp_path)
    state = RunState(
        job_id="j1", project_name="剑客", phase=PHASE_WRITING,
        current_chapter=5, total_chapters=10,
    )
    state.save(Path(orch.cfg.knowledge_dir) / "run_state.json")
    plan = TaskPlan(
        job_id="j1", brief="剑客", total_chapters=10,
        tasks=[
            Task(id=1, name="调研", phase=PHASE_RESEARCH, status=TASK_DONE),
            Task(id=2, name="写作", phase=PHASE_WRITING, status=TASK_RUNNING),
        ],
    )
    plan.save(Path(orch.cfg.knowledge_dir) / "task_plan.json")

    orch2 = _make_orch(tmp_path)
    from main import _detect_resumable_run
    info = _detect_resumable_run(orch2)
    assert info is not None
    # running 被重置为 pending
    assert info["pending_tasks"] == 1
    assert info["failed_tasks"] == 0


# ── 2. /resume 命令 ──────────────────────────────────────────


def test_resume_command_continues_unfinished(tmp_path: Path, monkeypatch, capsys):
    """/resume 从 task_plan.json 断点继续执行 pending 任务。"""
    orch = _make_orch(tmp_path)
    state = RunState(
        job_id="j1", project_name="剑客", phase=PHASE_WRITING,
        current_chapter=3, total_chapters=5,
    )
    state.save(Path(orch.cfg.knowledge_dir) / "run_state.json")
    plan = TaskPlan(
        job_id="j1", brief="剑客", total_chapters=5,
        tasks=[
            Task(id=1, name="写作", phase=PHASE_WRITING, status=TASK_DONE),
            Task(id=2, name="完稿", phase=PHASE_COMPLETE, status=TASK_PENDING),
        ],
    )
    plan.save(Path(orch.cfg.knowledge_dir) / "task_plan.json")

    # 重新加载
    orch = _make_orch(tmp_path)

    # mock phase_complete 为 no-op
    async def _noop_complete(self, *a, **kw):
        return "完稿ok"
    from orchestrator import StoryOrchestrator
    monkeypatch.setattr(StoryOrchestrator, "phase_complete", _noop_complete)

    from main import _dispatch_command
    _run(_dispatch_command("/resume", orch))
    out = capsys.readouterr().out

    assert "断点恢复" in out or "恢复" in out
    assert "完成" in out

    # 完稿任务应变为 done
    reloaded = TaskPlan.load(Path(orch.cfg.knowledge_dir) / "task_plan.json")
    assert reloaded.tasks[1].status == TASK_DONE


def test_resume_no_plan_prints_hint(tmp_path: Path, capsys):
    """/resume 无 task_plan 时打印提示，不报错。"""
    orch = _make_orch(tmp_path)
    from main import _dispatch_command
    _run(_dispatch_command("/resume", orch))
    out = capsys.readouterr().out
    assert "没有可恢复" in out or "无 task_plan" in out


def test_resume_all_done_prints_hint(tmp_path: Path, capsys):
    """/resume 所有任务已完成时打印提示。"""
    orch = _make_orch(tmp_path)
    plan = TaskPlan(
        job_id="j1", brief="剑客", total_chapters=5,
        tasks=[
            Task(id=1, name="完稿", phase=PHASE_COMPLETE, status=TASK_DONE),
        ],
    )
    plan.save(Path(orch.cfg.knowledge_dir) / "task_plan.json")
    orch = _make_orch(tmp_path)

    from main import _dispatch_command
    _run(_dispatch_command("/resume", orch))
    out = capsys.readouterr().out
    assert "已完成" in out


# ── 3. /discard 命令 ─────────────────────────────────────────


def test_discard_archives_state_and_plan(tmp_path: Path, capsys):
    """/discard 把 run_state.json + task_plan.json 移到 archive/{ts}/。"""
    orch = _make_orch(tmp_path)
    state = RunState(
        job_id="j1", project_name="剑客", phase=PHASE_WRITING,
        current_chapter=3, total_chapters=5,
    )
    state.save(Path(orch.cfg.knowledge_dir) / "run_state.json")
    plan = TaskPlan(
        job_id="j1", brief="剑客", total_chapters=5,
        tasks=[Task(id=1, name="写作", phase=PHASE_WRITING, status=TASK_PENDING)],
    )
    plan.save(Path(orch.cfg.knowledge_dir) / "task_plan.json")

    from main import _dispatch_command
    _run(_dispatch_command("/discard", orch))
    out = capsys.readouterr().out
    assert "归档" in out

    kd = Path(orch.cfg.knowledge_dir)
    # 原文件应已移走
    assert not (kd / "run_state.json").exists()
    assert not (kd / "task_plan.json").exists()
    # archive 下应有归档
    archive_root = kd / "archive"
    assert archive_root.exists()
    archived = list(archive_root.glob("*/"))
    assert len(archived) == 1
    moved = [p.name for p in archived[0].iterdir()]
    assert "run_state.json" in moved
    assert "task_plan.json" in moved


def test_discard_no_state_prints_hint(tmp_path: Path, capsys):
    """/discard 无可放弃运行时打印提示。"""
    orch = _make_orch(tmp_path)
    from main import _dispatch_command
    _run(_dispatch_command("/discard", orch))
    out = capsys.readouterr().out
    assert "没有可放弃" in out


# ── 4. 启动提示 ──────────────────────────────────────────────


def test_resume_hint_printed_on_startup(tmp_path: Path, capsys, monkeypatch):
    """main_interactive 启动时检测到未完成运行应打印恢复提示。"""
    orch = _make_orch(tmp_path)
    state = RunState(
        job_id="j1", project_name="剑客", phase=PHASE_WRITING,
        current_chapter=3, total_chapters=10,
    )
    state.save(Path(orch.cfg.knowledge_dir) / "run_state.json")
    plan = TaskPlan(
        job_id="j1", brief="剑客", total_chapters=10,
        tasks=[Task(id=1, name="写作", phase=PHASE_WRITING, status=TASK_PENDING)],
    )
    plan.save(Path(orch.cfg.knowledge_dir) / "task_plan.json")

    orch = _make_orch(tmp_path)

    # 让 main_interactive 立即退出（模拟 input 抛 EOFError）
    import main as main_mod
    inputs = iter([])  # 空 → 第一次 input 抛 StopIteration → 被 except 捕获

    def _fake_input(_prompt):
        raise EOFError
    monkeypatch.setattr("builtins.input", _fake_input)

    _run(main_mod.main_interactive(orch))
    out = capsys.readouterr().out
    assert "未完成" in out or "恢复" in out
    assert "/resume" in out
    assert "/discard" in out
