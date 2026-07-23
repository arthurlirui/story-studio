"""JobRunner batch 模式测试：write_mode=batch 走批量分支，progress 正确推进。

用 monkeypatch 替换 StoryOrchestrator.phase_writing_batch 计数调用，不调真 LLM。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from config import StudioConfig
from jobs import JobRunner, JOB_SUCCEEDED


def _cfg(tmp_path: Path) -> StudioConfig:
    return StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=2,
        main_model="test-main",
        light_model="test-light",
        batch_size=2,
        max_rounds=1,
    )


@pytest.fixture
def fake_run_pipeline(monkeypatch):
    """替换 orchestrator 的各 phase 方法为 no-op，仅记录 batch 调用次数。"""
    calls = {"batch": [], "writing": 0}

    async def _noop(self, *a, **kw):
        return "ok"

    async def _phase_writing(self, ch=None):
        calls["writing"] += 1
        return "ok"

    async def _phase_writing_batch(self, start, count):
        calls["batch"].append((start, count))
        return "ok"

    # 延迟导入避免循环
    from orchestrator import StoryOrchestrator
    monkeypatch.setattr(StoryOrchestrator, "phase_planning", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_building", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_outlining", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_writing", _phase_writing)
    monkeypatch.setattr(StoryOrchestrator, "phase_writing_batch", _phase_writing_batch)
    monkeypatch.setattr(StoryOrchestrator, "phase_complete", _noop)
    # total_chapters 由 phase_outlining 写入；直接给个 attr
    async def _outlining(self, total_chapters=None):
        self.total_chapters = total_chapters or 4
        return "ok"
    monkeypatch.setattr(StoryOrchestrator, "phase_outlining", _outlining)
    return calls


def test_batch_mode_calls_phase_writing_batch(tmp_path: Path, fake_run_pipeline):
    """write_mode=batch 应调用 phase_writing_batch，不调 phase_writing。"""
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path),
                           max_concurrent=2)
        job_id = await runner.submit(
            "测试", project_name="测试", total_chapters=4, write_mode="batch",
        )
        # 等后台任务完成
        for _ in range(50):
            await asyncio.sleep(0.05)
            if runner.get(job_id).status in (JOB_SUCCEEDED, "failed", "cancelled"):
                break
        return job_id

    job_id = _run(_go())
    calls = fake_run_pipeline
    # batch_size=2, total=4 → 应分 2 批：(1,2) 和 (3,2)
    assert calls["batch"] == [(1, 2), (3, 2)]
    assert calls["writing"] == 0  # 不应走串行分支


def test_sequential_mode_still_works(tmp_path: Path, fake_run_pipeline):
    """write_mode=sequential 应走 phase_writing 串行，不调 batch。"""
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path),
                           max_concurrent=2)
        job_id = await runner.submit(
            "测试", project_name="测试", total_chapters=3, write_mode="sequential",
        )
        for _ in range(50):
            await asyncio.sleep(0.05)
            if runner.get(job_id).status in (JOB_SUCCEEDED, "failed", "cancelled"):
                break
        return job_id

    _run(_go())
    calls = fake_run_pipeline
    assert calls["batch"] == []
    assert calls["writing"] == 3


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
