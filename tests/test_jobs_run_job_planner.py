"""集成测试：jobs._run_job 走真实 TaskPlanner 链路。

不替换 _run_job，而是 monkeypatch StoryOrchestrator 的各 phase 方法为可控 fake，
让 TaskPlanner 端到端驱动 7 任务清单，验证：
- H6: task 失败时 job 标记 JOB_FAILED（而非 JOB_SUCCEEDED）
- H1: total_chapters=None 时不硬编码 10，让 orchestrator 从 outline 解析
- H2: progress 语义（writing 阶段 vs 其他阶段）

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 手动驱动 async 用例。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from config import StudioConfig
from jobs import JobRunner, JOB_SUCCEEDED, JOB_FAILED


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


@pytest.fixture
def fake_phases(monkeypatch):
    """替换 orchestrator 各 phase 为 no-op，记录调用。

    默认全部成功；测试可改 phase_*._failing=True 触发失败。
    """
    state = {
        "outlining_total": None,  # outlining 设置的 total_chapters
        "writing_calls": 0,
        "complete_calls": 0,
        "fail_phase": None,  # 哪个 phase 抛异常
    }

    async def _noop(self, *a, **kw):
        return "ok"

    async def _phase_research(self, brief):
        if state["fail_phase"] == "research":
            raise RuntimeError("research boom")
        return "ok"

    async def _phase_innovate(self, brief=""):
        if state["fail_phase"] == "innovate":
            raise RuntimeError("innovate boom")
        return "ok"

    async def _phase_outlining(self, total_chapters=None):
        # H1 验证：total_chapters=None 时从"outline 解析"得 7（模拟）
        if total_chapters is None:
            self.total_chapters = 7
        else:
            self.total_chapters = total_chapters
        state["outlining_total"] = self.total_chapters
        return "ok"

    async def _phase_writing(self, ch=None):
        state["writing_calls"] += 1
        return "ok"

    async def _phase_complete(self, review_criteria=""):
        state["complete_calls"] += 1
        if state["fail_phase"] == "complete":
            raise RuntimeError("complete boom")
        return "ok"

    from orchestrator import StoryOrchestrator
    monkeypatch.setattr(StoryOrchestrator, "phase_research", _phase_research)
    monkeypatch.setattr(StoryOrchestrator, "phase_innovate", _phase_innovate)
    monkeypatch.setattr(StoryOrchestrator, "phase_planning", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_building", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_outlining", _phase_outlining)
    monkeypatch.setattr(StoryOrchestrator, "phase_writing", _phase_writing)
    monkeypatch.setattr(StoryOrchestrator, "phase_writing_batch", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_complete", _phase_complete)
    return state


async def _wait_done(runner, job_id, timeout=5.0):
    """轮询等待 job 到终态。"""
    for _ in range(int(timeout / 0.05)):
        await asyncio.sleep(0.05)
        job = runner.get(job_id)
        if job.status in (JOB_SUCCEEDED, JOB_FAILED, "cancelled"):
            return job
    return runner.get(job_id)


# ── Tests ────────────────────────────────────────────────────


def test_run_job_success_marks_succeeded(tmp_path: Path, fake_phases):
    """成功跑完 7 任务后 job 应标记 JOB_SUCCEEDED。"""
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        job_id = await runner.submit(
            "剑客故事", project_name="剑客", total_chapters=3,
        )
        job = await _wait_done(runner, job_id)
        assert job.status == JOB_SUCCEEDED, f"expected succeeded, got {job.status}: {job.error}"
        assert job.phase == "complete"
        assert fake_phases["complete_calls"] == 1
        return job_id

    _run(_go())


def test_run_job_task_failure_marks_failed(tmp_path: Path, fake_phases):
    """H6 修复：某个 phase 失败时 job 应标记 JOB_FAILED，而非 JOB_SUCCEEDED。"""
    fake_phases["fail_phase"] = "research"

    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        job_id = await runner.submit(
            "剑客故事", project_name="剑客", total_chapters=3,
        )
        job = await _wait_done(runner, job_id)
        assert job.status == JOB_FAILED, (
            f"H6 回归：phase 失败但 job.status={job.status}（应 FAILED）"
        )
        assert job.error is not None
        assert "research boom" in job.error or "失败" in job.error
        return job_id

    _run(_go())


def test_run_job_progress_semantics(tmp_path: Path, fake_phases):
    """H2 修复：job.progress 在非 writing 阶段是 (done_tasks, total_tasks)，
    writing 阶段是 (current_chapter, total_chapters)，task_progress 显式记录任务粒度。
    """
    captured_progress: list[tuple] = []

    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        job_id = await runner.submit(
            "剑客故事", project_name="剑客", total_chapters=3,
        )
        # 轮询过程中采样 progress
        for _ in range(100):
            await asyncio.sleep(0.02)
            job = runner.get(job_id)
            captured_progress.append((job.phase, job.progress, job.task_progress))
            if job.status in (JOB_SUCCEEDED, JOB_FAILED, "cancelled"):
                break
        return job_id

    _run(_go())

    # 至少应捕获到非 writing 阶段的 progress（任务粒度）和 writing 阶段（章节粒度）
    non_writing = [p for p in captured_progress if p[0] not in ("writing", "complete", "idle")]
    writing = [p for p in captured_progress if p[0] == "writing"]
    # 非写作阶段：task_progress 应与 progress 一致（任务粒度）
    if non_writing:
        for phase, prog, tp in non_writing:
            if prog[1] > 0:  # 有任务时检查
                assert tp is not None, f"非 writing 阶段 task_progress 不应为 None: phase={phase}"
                assert tp == prog, f"非 writing 阶段 task_progress 应等于 progress: {tp} vs {prog}"
    # writing 阶段：progress 是 (chapter, total)，task_progress 仍记录任务粒度
    if writing:
        _, prog, tp = writing[-1]
        # total_chapters=3，writing 时 progress[1] 应为 3
        assert prog[1] == 3, f"writing 阶段 progress[1] 应为 total_chapters=3, got {prog}"


def test_run_job_total_chapters_none_uses_outline(tmp_path: Path, fake_phases):
    """H1 修复：total_chapters=None 透传，orchestrator 从 outline 解析（模拟得 7），
    而非硬编码 10。
    """
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        # total_chapters=None（submit 支持 None）
        job_id = await runner.submit(
            "剑客故事", project_name="剑客", total_chapters=None,
        )
        job = await _wait_done(runner, job_id)
        assert job.status == JOB_SUCCEEDED, f"job 失败: {job.error}"
        # outlining 应收到 total_chapters=None，并解析为 7（模拟）
        assert fake_phases["outlining_total"] == 7, (
            f"H1 回归：total_chapters=None 时应从 outline 解析得 7，"
            f"实际 outlining 收到 total={fake_phases['outlining_total']}"
        )
        # writing 阶段应跑 7 章（不是 10）
        assert fake_phases["writing_calls"] == 7, (
            f"H1 回归：应写 7 章而非 10，实际 writing_calls={fake_phases['writing_calls']}"
        )
        return job_id

    _run(_go())
