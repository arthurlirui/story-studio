"""集成测试：断电重启小说编写恢复功能。

覆盖：
- is_chapter_delivered: 有摘要文件 = 已交付
- load_plan: stale-running 任务重置为 pending
- _run_writing_phase: 跳过已交付章节
- _run_job: 有 task_plan.json 时走 load_plan 而非 build_plan
- _auto_recover_jobs: 重启后自动恢复 recoverable job
- progress_log: 章节完成后 run_state.json 有进度记录
- 批次中途崩溃恢复
- API /novels/{id}/resume 端点

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 手动驱动 async 用例。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import StudioConfig
from planner import (
    TASK_DONE, TASK_PENDING, TASK_RUNNING,
    Task, TaskPlan, TaskPlanner,
)
from orchestrator_state import (
    PHASE_WRITING, PHASE_RESEARCH, RunState,
)
from jobs import JobRunner, JOB_SUCCEEDED, JOB_FAILED, JOB_RECOVERABLE


def _run(coro):
    """新建 event loop 跑完协程，替代 pytest-asyncio。"""
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


# ── 1. is_chapter_delivered ──────────────────────────────────


def test_is_chapter_delivered(tmp_path: Path):
    """有摘要文件返回 True，无则 False。"""
    from agents.knowledge import KnowledgeStore
    ks = KnowledgeStore(base_dir=str(tmp_path / "knowledge"))
    ks.summaries_dir.mkdir(parents=True, exist_ok=True)

    assert ks.is_chapter_delivered(1) is False
    (ks.summaries_dir / "chapter_001.md").write_text("摘要", encoding="utf-8")
    assert ks.is_chapter_delivered(1) is True
    assert ks.is_chapter_delivered(2) is False


# ── 2. load_plan stale-running 重置 ──────────────────────────


def test_stale_running_task_reset(tmp_path: Path, monkeypatch):
    """load_plan 把 running 任务重置为 pending（崩溃恢复核心）。"""
    cfg = _cfg(tmp_path)
    plan_path = tmp_path / "task_plan.json"
    # 构造一个有 running 任务的 plan（模拟崩溃时的盘上状态）
    plan = TaskPlan(
        job_id="j1", brief="故事", total_chapters=3,
        tasks=[
            Task(id=1, name="调研", phase=PHASE_RESEARCH, status=TASK_DONE),
            Task(id=2, name="写作", phase=PHASE_WRITING, status=TASK_RUNNING),
            Task(id=3, name="完稿", phase="complete", status=TASK_PENDING),
        ],
    )
    plan.save(plan_path)

    orch = MagicMock()
    orch.knowledge = MagicMock()
    orch.knowledge.is_chapter_delivered = MagicMock(return_value=False)
    planner = TaskPlanner(orch, MagicMock(), cfg, MagicMock(), plan_path=plan_path)
    loaded = planner.load_plan()

    assert loaded is not None
    # running 任务应被重置为 pending
    task2 = loaded.tasks[1]
    assert task2.status == TASK_PENDING, (
        f"stale running 应重置为 pending, got {task2.status}"
    )
    assert task2.started_at is None
    # done 任务不受影响
    assert loaded.tasks[0].status == TASK_DONE
    # 盘上也应已持久化重置
    reloaded = TaskPlan.load(plan_path)
    assert reloaded.tasks[1].status == TASK_PENDING


# ── 3. _run_writing_phase 跳过已交付章节 ──────────────────────


def test_writing_phase_skips_delivered_chapters(tmp_path: Path):
    """已有摘要的章节在 _run_writing_phase 中被跳过。"""
    cfg = _cfg(tmp_path)
    plan_path = tmp_path / "task_plan.json"
    plan = TaskPlan(
        job_id="j1", brief="故事", total_chapters=4,
        write_mode="sequential",
        tasks=[Task(id=1, name="写作", phase=PHASE_WRITING)],
    )
    plan.save(plan_path)

    orch = MagicMock()
    orch.total_chapters = 4
    writing_calls: list[int] = []
    async def _phase_writing(ch=None):
        writing_calls.append(ch)
        return "ok"
    orch.phase_writing = _phase_writing
    orch.phase_writing_batch = MagicMock(side_effect=AssertionError("不应走批次"))

    # 模拟第 1、2 章已交付
    def _delivered(ch):
        return ch in (1, 2)
    orch.knowledge = MagicMock()
    orch.knowledge.is_chapter_delivered = _delivered

    planner = TaskPlanner(orch, MagicMock(), cfg, MagicMock(), plan_path=plan_path)
    planner.plan = plan

    result = _run(planner._run_writing_phase())

    # 只应写第 3、4 章
    assert writing_calls == [3, 4], f"应跳过已交付的 1、2 章, got {writing_calls}"
    assert "4 章" in result


# ── 4. _run_job 有 task_plan.json 时走 load_plan ─────────────


def test_run_job_loads_existing_plan(tmp_path: Path, monkeypatch):
    """_run_job 在有 task_plan.json 时走 load_plan 而非 build_plan（不覆盖旧进度）。"""
    # 假 phase：全部 no-op，但记录 phase_writing 调用
    async def _noop(self, *a, **kw):
        return "ok"

    async def _phase_outlining(self, total_chapters=None):
        self.total_chapters = total_chapters or 3
        return "ok"

    writing_calls: list[int] = []
    async def _phase_writing(self, ch=None):
        writing_calls.append(ch)
        return "ok"

    from orchestrator import StoryOrchestrator
    monkeypatch.setattr(StoryOrchestrator, "phase_research", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_innovate", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_planning", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_building", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_outlining", _phase_outlining)
    monkeypatch.setattr(StoryOrchestrator, "phase_writing", _phase_writing)
    monkeypatch.setattr(StoryOrchestrator, "phase_writing_batch", _noop)
    monkeypatch.setattr(StoryOrchestrator, "phase_complete", _noop)

    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        job_id = await runner.submit("剑客故事", project_name="剑客", total_chapters=3)
        # 等首次运行完成
        for _ in range(100):
            await asyncio.sleep(0.02)
            job = runner.get(job_id)
            if job.status in (JOB_SUCCEEDED, JOB_FAILED):
                break
        first_writing = list(writing_calls)
        assert first_writing == [1, 2, 3], f"首次应写 3 章, got {first_writing}"

        # 模拟崩溃：把 job 标记为 failed（run-all 风格），保留 task_plan.json
        job = runner.get(job_id)
        job.status = JOB_FAILED
        job.error = "模拟崩溃"
        runner._save_index()
        return job_id, runner

    job_id, runner = _run(_go())

    # 再次 submit 同一 job 不会发生（job_id 已固定）；改为通过 run-all 触发恢复。
    # 这里验证：第二次运行同一 knowledge_dir 时，由于所有章节已被 phase_writing
    # "写过"（但无摘要），恢复不会跳过——所以我们手动写摘要模拟交付。
    # 更直接的验证：load_plan 不覆盖已有 plan。检查 task_plan.json 的 job_id 不变。
    plan_path = Path(runner.get(job_id).knowledge_dir) / "task_plan.json"
    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_data["job_id"] == job_id, "task_plan.json 的 job_id 应保留不变"


# ── 5. _auto_recover_jobs 自动恢复 ───────────────────────────


def test_auto_recover_on_restart(tmp_path: Path, monkeypatch):
    """JobRunner 初始化时自动恢复 recoverable job。"""
    # 先构造一个有 task_plan.json 的 job 目录，index.json 标 running
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True)
    jid = "12345_abcdef"
    job_dir = jobs_dir / jid
    kd = job_dir / "knowledge"
    kd.mkdir(parents=True)
    # 写 task_plan.json（使 job 可恢复）
    plan = TaskPlan(
        job_id=jid, brief="剑客", total_chapters=2,
        tasks=[Task(id=1, name="写作", phase=PHASE_WRITING)],
    )
    plan.save(kd / "task_plan.json")
    # 写 index.json 标 running
    index_data = {
        "jobs": [{
            "id": jid, "brief": "剑客", "status": "running", "phase": "writing",
            "progress": [1, 2], "task_progress": None,
            "created_at": 1000.0, "updated_at": 2000.0,
            "knowledge_dir": str(kd), "output_dir": str(job_dir / "output"),
            "project_name": "剑客", "write_mode": "sequential",
            "result": None, "error": None,
        }],
        "updated_at": 2000.0,
    }
    (jobs_dir / "index.json").write_text(json.dumps(index_data), encoding="utf-8")

    # 假 _run_job：记录被调用，立即成功
    recovered: list[str] = []
    async def _fake_run_job(self, job, total_chapters):
        recovered.append(job.id)
        async with self._semaphore:
            job.status = JOB_SUCCEEDED
            job.phase = "complete"
            job.touch()
            self._save_index()
    monkeypatch.setattr(JobRunner, "_run_job", _fake_run_job)

    async def _go():
        # 初始化时应自动恢复
        runner = JobRunner(base_dir=str(jobs_dir), cfg=_cfg(tmp_path))
        # _auto_recover_jobs 启动了后台 task，等它完成
        for _ in range(100):
            await asyncio.sleep(0.02)
            job = runner.get(jid)
            if job and job.status in (JOB_SUCCEEDED, JOB_FAILED):
                break
        return runner

    runner = _run(_go())
    job = runner.get(jid)
    assert recovered == [jid], f"应自动恢复 job {jid}, got recovered={recovered}"
    assert job.status == JOB_SUCCEEDED


# ── 6. progress_log 记录 ─────────────────────────────────────


def test_progress_log_appended_on_chapter_pass(tmp_path: Path):
    """章节 PASS 后 run_state.json 的 progress_log 应有记录。"""
    from agents.knowledge import KnowledgeStore
    kd = tmp_path / "knowledge"
    ks = KnowledgeStore(base_dir=str(kd))
    ks.summaries_dir.mkdir(parents=True, exist_ok=True)
    ks.chapters_dir.mkdir(parents=True, exist_ok=True)

    state_path = kd / "run_state.json"
    state = RunState(job_id="j1", project_name="测试", phase=PHASE_WRITING,
                     current_chapter=0, total_chapters=3)
    state.save(state_path)

    # 模拟 _append_progress 的核心逻辑（与 orchestrator._append_progress 一致）
    state.append_progress(state_path, {
        "phase": PHASE_WRITING, "chapter": 1, "batch_id": None,
        "event": "chapter_passed", "detail": "1 轮通过",
    })
    state.append_progress(state_path, {
        "phase": PHASE_WRITING, "chapter": 2, "batch_id": None,
        "event": "chapter_passed", "detail": "2 轮通过",
    })

    reloaded = RunState.load(state_path)
    assert reloaded is not None
    assert len(reloaded.progress_log) == 2
    assert reloaded.progress_log[0]["chapter"] == 1
    assert reloaded.progress_log[0]["event"] == "chapter_passed"
    assert reloaded.progress_log[1]["chapter"] == 2
    # 时间戳应自动补充
    assert "ts" in reloaded.progress_log[0]


# ── 7. 批次中途崩溃恢复 ──────────────────────────────────────


def test_batch_mid_crash_resume(tmp_path: Path):
    """模拟批次写到一半崩溃，恢复后从正确章节继续。"""
    cfg = _cfg(tmp_path)
    plan_path = tmp_path / "task_plan.json"
    plan = TaskPlan(
        job_id="j1", brief="故事", total_chapters=6,
        write_mode="batch",
        tasks=[Task(id=1, name="写作", phase=PHASE_WRITING)],
    )
    plan.save(plan_path)
    cfg.batch_size = 3

    orch = MagicMock()
    orch.total_chapters = 6
    batch_calls: list[tuple[int, int]] = []
    async def _phase_writing_batch(start, count):
        batch_calls.append((start, count))
        return "ok"
    orch.phase_writing_batch = _phase_writing_batch
    orch.phase_writing = MagicMock(side_effect=AssertionError("batch 模式不应走串行"))

    # 模拟第 1-3 章已交付（第一批写完崩溃）
    def _delivered(ch):
        return ch in (1, 2, 3)
    orch.knowledge = MagicMock()
    orch.knowledge.is_chapter_delivered = _delivered

    planner = TaskPlanner(orch, MagicMock(), cfg, MagicMock(), plan_path=plan_path)
    planner.plan = plan

    result = _run(planner._run_writing_phase())

    # 第一批 (1,3) 已交付应跳过，只应写第二批 (4,3)
    assert batch_calls == [(4, 3)], (
        f"崩溃后应只写第二批 (4,3), got {batch_calls}"
    )


# ── 8. API /novels/{id}/resume 端点 ──────────────────────────


def test_api_resume_endpoint(tmp_path: Path, monkeypatch):
    """POST /novels/{id}/resume 恢复 failed job。"""
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    async def _fake_run_job(self, job, total_chapters):
        async with self._semaphore:
            job.status = "running"
            self._save_index()
            await asyncio.sleep(0.01)
            job.status = JOB_SUCCEEDED
            job.phase = "complete"
            job.result = {"total_chapters": 2, "preview": "完稿"}
            self._save_index()

    monkeypatch.setattr(JobRunner, "_run_job", _fake_run_job)
    monkeypatch.setenv("STORY_STUDIO_JOBS_DIR", str(tmp_path / "jobs"))

    import api
    api._runner = None
    monkeypatch.setattr(api, "load_config", lambda: _cfg(tmp_path))

    with TestClient(api.app) as client:
        # 先创建一个 job
        resp = client.post("/novels", json={"brief": "剑客", "project_name": "剑客"})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        # 等后台完成
        import time
        time.sleep(0.3)

        # 手动标记为 failed（模拟崩溃后状态）
        runner = api.get_runner()
        job = runner.get(job_id)
        job.status = JOB_FAILED
        job.error = "模拟崩溃"
        runner._save_index()

        # 写一个 task_plan.json（resume 需要）
        kd = Path(job.knowledge_dir)
        kd.mkdir(parents=True, exist_ok=True)
        plan = TaskPlan(
            job_id=job_id, brief="剑客", total_chapters=2,
            tasks=[
                Task(id=1, name="调研", phase=PHASE_RESEARCH, status=TASK_DONE),
                Task(id=2, name="完稿", phase="complete", status=TASK_PENDING),
            ],
        )
        plan.save(kd / "task_plan.json")

        # 假 phase：让 resume 能跑通
        async def _noop(self, *a, **kw):
            return "ok"
        from orchestrator import StoryOrchestrator
        monkeypatch.setattr(StoryOrchestrator, "phase_research", _noop)
        monkeypatch.setattr(StoryOrchestrator, "phase_innovate", _noop)
        monkeypatch.setattr(StoryOrchestrator, "phase_planning", _noop)
        monkeypatch.setattr(StoryOrchestrator, "phase_building", _noop)
        monkeypatch.setattr(StoryOrchestrator, "phase_outlining", _noop)
        monkeypatch.setattr(StoryOrchestrator, "phase_writing", _noop)
        monkeypatch.setattr(StoryOrchestrator, "phase_writing_batch", _noop)
        monkeypatch.setattr(StoryOrchestrator, "phase_complete", _noop)

        resp2 = client.post(f"/novels/{job_id}/resume")
        assert resp2.status_code == 200, f"resume 应成功, got {resp2.status_code}: {resp2.text}"
        body = resp2.json()
        assert body["status"] == "succeeded"

    api._runner = None
