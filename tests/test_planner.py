"""单元测试：planner.py 的 TaskPlanner / Task / TaskPlan。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import StudioConfig
from planner import (
    TASK_DONE, TASK_FAILED, TASK_PENDING, TASK_RUNNING, TASK_SKIPPED,
    Task, TaskPlan, TaskPlanner,
)
from orchestrator_state import (
    PHASE_BUILDING, PHASE_COMPLETE, PHASE_INNOVATE, PHASE_OUTLINING,
    PHASE_PLANNING, PHASE_RESEARCH, PHASE_WRITING,
)


@pytest.fixture
def cfg(tmp_path: Path) -> StudioConfig:
    return StudioConfig(
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
    )


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    orch = MagicMock()
    orch.job_id = "test_job_123"
    orch.project_name = "测试项目"
    orch.total_chapters = 5
    orch.current_chapter = 0
    orch.phase_research = AsyncMock(return_value="调研完成")
    orch.phase_innovate = AsyncMock(return_value="创新亮点清单")
    orch.phase_planning = AsyncMock(return_value="企划完成")
    orch.phase_building = AsyncMock(return_value="设定完成")
    orch.phase_outlining = AsyncMock(return_value="大纲完成")
    orch.phase_writing = AsyncMock(return_value="章节完成")
    orch.phase_writing_batch = AsyncMock(return_value="批次完成")
    orch.phase_complete = AsyncMock(return_value="完稿")
    return orch


@pytest.fixture
def mock_worklog() -> MagicMock:
    wl = MagicMock()
    wl.append = AsyncMock()
    return wl


@pytest.fixture
def planner(
    mock_orchestrator: MagicMock, cfg: StudioConfig,
    mock_worklog: MagicMock, tmp_path: Path,
) -> TaskPlanner:
    return TaskPlanner(
        mock_orchestrator, MagicMock(), cfg, mock_worklog,
        plan_path=tmp_path / "task_plan.json",
    )


# ── Task / TaskPlan 数据结构 ──────────────────────────────────

class TestTask:
    def test_to_dict(self):
        t = Task(id=1, name="调研", phase=PHASE_RESEARCH)
        d = t.to_dict()
        assert d["id"] == 1
        assert d["phase"] == PHASE_RESEARCH
        assert d["status"] == TASK_PENDING


class TestTaskPlan:
    def test_save_and_load(self, tmp_path: Path):
        plan_path = tmp_path / "task_plan.json"
        plan = TaskPlan(
            job_id="j1", brief="故事", total_chapters=3,
            write_mode="batch",
            tasks=[Task(id=1, name="调研", phase=PHASE_RESEARCH)],
        )
        plan.save(plan_path)
        loaded = TaskPlan.load(plan_path)
        assert loaded is not None
        assert loaded.job_id == "j1"
        assert loaded.total_chapters == 3
        assert loaded.write_mode == "batch"
        assert len(loaded.tasks) == 1
        assert loaded.tasks[0].phase == PHASE_RESEARCH

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert TaskPlan.load(tmp_path / "nonexistent.json") is None

    def test_load_corrupt_returns_none(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        assert TaskPlan.load(bad) is None


# ── TaskPlanner.build_plan ────────────────────────────────────

class TestBuildPlan:
    def test_generates_7_tasks(self, planner: TaskPlanner):
        plan = planner.build_plan(brief="测试", total_chapters=10)
        assert len(plan.tasks) == 7
        phases = [t.phase for t in plan.tasks]
        assert phases == [
            PHASE_RESEARCH, PHASE_INNOVATE, PHASE_PLANNING,
            PHASE_BUILDING, PHASE_OUTLINING, PHASE_WRITING, PHASE_COMPLETE,
        ]

    def test_all_pending_initially(self, planner: TaskPlanner):
        plan = planner.build_plan(brief="测试", total_chapters=5)
        assert all(t.status == TASK_PENDING for t in plan.tasks)

    def test_research_disabled_marks_skipped(self, planner: TaskPlanner):
        planner.cfg.research_enabled = False
        plan = planner.build_plan(brief="测试", total_chapters=5)
        research_task = next(t for t in plan.tasks if t.phase == PHASE_RESEARCH)
        innovate_task = next(t for t in plan.tasks if t.phase == PHASE_INNOVATE)
        assert research_task.status == TASK_SKIPPED
        assert innovate_task.status == TASK_SKIPPED
        # 其他任务仍 pending
        others = [t for t in plan.tasks if t.phase not in (PHASE_RESEARCH, PHASE_INNOVATE)]
        assert all(t.status == TASK_PENDING for t in others)

    def test_saves_to_disk(self, planner: TaskPlanner):
        plan = planner.build_plan(brief="测试", total_chapters=5)
        assert planner.plan_path.exists()
        # 加载应一致
        loaded = TaskPlan.load(planner.plan_path)
        assert loaded is not None
        assert len(loaded.tasks) == 7

    def test_invalid_write_mode_falls_back(self, planner: TaskPlanner):
        plan = planner.build_plan(brief="测试", total_chapters=5, write_mode="invalid")
        assert plan.write_mode == "sequential"


# ── TaskPlanner 查询 ──────────────────────────────────────────

class TestQuery:
    def test_next_task_returns_first_pending(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        nxt = planner.next_task()
        assert nxt is not None
        assert nxt.phase == PHASE_RESEARCH

    def test_next_task_skips_done(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        planner.plan.tasks[0].status = TASK_DONE
        planner.plan.tasks[1].status = TASK_DONE
        nxt = planner.next_task()
        assert nxt is not None
        assert nxt.phase == PHASE_PLANNING

    def test_next_task_none_when_all_done(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        for t in planner.plan.tasks:
            t.status = TASK_DONE
        assert planner.next_task() is None

    def test_next_task_skips_failed_until_reset(self, planner: TaskPlanner):
        # failed 任务不会被 next_task 自动重试，需显式 reset_task
        planner.build_plan(brief="测试", total_chapters=5)
        planner.plan.tasks[0].status = TASK_DONE
        planner.plan.tasks[1].status = TASK_FAILED
        # 失败的 innovate 不应被选中，应跳到 planning
        nxt = planner.next_task()
        assert nxt is not None
        assert nxt.phase == PHASE_PLANNING
        # reset 后才会被选中
        planner.reset_task(2)
        nxt = planner.next_task()
        assert nxt is not None
        assert nxt.phase == PHASE_INNOVATE

    def test_next_task_skips_skipped(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        planner.plan.tasks[0].status = TASK_SKIPPED
        nxt = planner.next_task()
        assert nxt is not None
        assert nxt.phase == PHASE_INNOVATE

    def test_summary_counts(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        planner.plan.tasks[0].status = TASK_DONE
        planner.plan.tasks[1].status = TASK_FAILED
        s = planner.summary()
        assert s["total"] == 7
        assert s["done"] == 1
        assert s["failed"] == 1
        assert s["pending"] == 5


# ── 状态变更 ──────────────────────────────────────────────────

class TestStateChange:
    def test_mark_done(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        planner.mark_done(1, result_excerpt="完成摘要")
        assert planner.plan.tasks[0].status == TASK_DONE
        assert planner.plan.tasks[0].result_excerpt == "完成摘要"
        assert planner.plan.tasks[0].completed_at is not None

    def test_mark_failed(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        planner.mark_failed(1, "出错原因")
        assert planner.plan.tasks[0].status == TASK_FAILED
        assert planner.plan.tasks[0].error == "出错原因"

    def test_reset_task(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        planner.mark_done(1, "完成")
        planner.reset_task(1)
        assert planner.plan.tasks[0].status == TASK_PENDING
        assert planner.plan.tasks[0].started_at is None
        assert planner.plan.tasks[0].completed_at is None
        assert planner.plan.tasks[0].result_excerpt == ""

    def test_mark_persists_to_disk(self, planner: TaskPlanner):
        planner.build_plan(brief="测试", total_chapters=5)
        planner.mark_done(1, "摘要")
        loaded = TaskPlan.load(planner.plan_path)
        assert loaded is not None
        assert loaded.tasks[0].status == TASK_DONE


# ── run_task 分派 ─────────────────────────────────────────────

class TestRunTask:
    @pytest.mark.asyncio
    async def test_dispatch_research(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试", total_chapters=5)
        task = planner.plan.tasks[0]  # research
        await planner.run_task(task)
        mock_orchestrator.phase_research.assert_awaited_once_with("测试")
        assert task.status == TASK_DONE

    @pytest.mark.asyncio
    async def test_dispatch_innovate(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试", total_chapters=5)
        task = planner.plan.tasks[1]  # innovate
        await planner.run_task(task)
        mock_orchestrator.phase_innovate.assert_awaited_once()
        assert task.status == TASK_DONE

    @pytest.mark.asyncio
    async def test_dispatch_planning(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试 brief", total_chapters=5)
        task = planner.plan.tasks[2]  # planning
        await planner.run_task(task)
        mock_orchestrator.phase_planning.assert_awaited_once_with("测试 brief")

    @pytest.mark.asyncio
    async def test_dispatch_outlining_passes_total(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试", total_chapters=7)
        task = planner.plan.tasks[4]  # outlining
        await planner.run_task(task)
        mock_orchestrator.phase_outlining.assert_awaited_once()
        call_kwargs = mock_orchestrator.phase_outlining.await_args.kwargs
        assert call_kwargs.get("total_chapters") == 7

    @pytest.mark.asyncio
    async def test_dispatch_writing_sequential(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试", total_chapters=3, write_mode="sequential")
        task = planner.plan.tasks[5]  # writing
        await planner.run_task(task)
        assert mock_orchestrator.phase_writing.await_count == 3
        mock_orchestrator.phase_writing_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_writing_batch(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试", total_chapters=5, write_mode="batch")
        planner.cfg.batch_size = 2
        task = planner.plan.tasks[5]  # writing
        await planner.run_task(task)
        # 5 章按 batch_size=2 应该跑 3 批 (2+2+1)
        assert mock_orchestrator.phase_writing_batch.await_count == 3
        mock_orchestrator.phase_writing.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failure_marks_failed_and_reraises(
        self, planner: TaskPlanner, mock_orchestrator,
    ):
        planner.build_plan(brief="测试", total_chapters=5)
        mock_orchestrator.phase_research.side_effect = RuntimeError("boom")
        task = planner.plan.tasks[0]
        with pytest.raises(RuntimeError, match="boom"):
            await planner.run_task(task)
        assert task.status == TASK_FAILED
        assert "boom" in (task.error or "")


# ── run_all ───────────────────────────────────────────────────

class TestRunAll:
    @pytest.mark.asyncio
    async def test_runs_all_pending_in_order(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试", total_chapters=2, write_mode="sequential")
        progress_log = []

        def on_progress(t):
            progress_log.append((t.id, t.status))

        await planner.run_all(on_progress=on_progress)

        # 所有 7 任务都应被回调
        assert len(progress_log) == 7
        # 第一个任务 id=1，最后一个 id=7
        assert progress_log[0][0] == 1
        assert progress_log[-1][0] == 7
        # 所有任务都 done
        assert all(t.status == TASK_DONE for t in planner.plan.tasks)
        # 每个方法都被调用
        mock_orchestrator.phase_research.assert_awaited_once()
        mock_orchestrator.phase_innovate.assert_awaited_once()
        mock_orchestrator.phase_planning.assert_awaited_once()
        mock_orchestrator.phase_building.assert_awaited_once()
        mock_orchestrator.phase_outlining.assert_awaited_once()
        mock_orchestrator.phase_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stops_on_failure(self, planner: TaskPlanner, mock_orchestrator):
        planner.build_plan(brief="测试", total_chapters=2)
        mock_orchestrator.phase_building.side_effect = RuntimeError("build 失败")
        await planner.run_all(stop_on_failure=True)
        # building 之前的任务应完成
        assert planner.plan.tasks[0].status == TASK_DONE  # research
        assert planner.plan.tasks[1].status == TASK_DONE  # innovate
        assert planner.plan.tasks[2].status == TASK_DONE  # planning
        # building 失败
        assert planner.plan.tasks[3].status == TASK_FAILED
        # outlining/writing/complete 未被触达
        assert planner.plan.tasks[4].status == TASK_PENDING
        assert planner.plan.tasks[5].status == TASK_PENDING
        mock_orchestrator.phase_outlining.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_continues_on_failure_when_configured(
        self, planner: TaskPlanner, mock_orchestrator,
    ):
        planner.build_plan(brief="测试", total_chapters=2, write_mode="sequential")
        # 让 building 失败但其它继续（注：outlining 依赖 building 产物，实际场景中
        # 下游会因无 world 而失败，这里只验证 stop_on_failure=False 的语义：
        # building 失败后仍会推进到下一个 pending 任务）
        mock_orchestrator.phase_building.side_effect = RuntimeError("build 失败")
        # 后续 phase 也跟着失败（无 world 产物）
        mock_orchestrator.phase_outlining.side_effect = RuntimeError("no world")
        mock_orchestrator.phase_writing.side_effect = RuntimeError("no outline")
        mock_orchestrator.phase_complete.side_effect = RuntimeError("no chapters")
        await planner.run_all(stop_on_failure=False)
        # 每个任务都应被触达（不再被 building 失败阻塞）
        mock_orchestrator.phase_building.assert_awaited_once()
        mock_orchestrator.phase_outlining.assert_awaited_once()
        mock_orchestrator.phase_complete.assert_awaited_once()
        # research/innovate/planning 成功，building/outlining/writing/complete 失败
        assert planner.plan.tasks[0].status == TASK_DONE  # research
        assert planner.plan.tasks[1].status == TASK_DONE  # innovate
        assert planner.plan.tasks[2].status == TASK_DONE  # planning
        assert planner.plan.tasks[3].status == TASK_FAILED  # building
        assert planner.plan.tasks[4].status == TASK_FAILED  # outlining
        assert planner.plan.tasks[5].status == TASK_FAILED  # writing
        assert planner.plan.tasks[6].status == TASK_FAILED  # complete

    @pytest.mark.asyncio
    async def test_resumes_from_existing_plan(
        self, planner: TaskPlanner, mock_orchestrator, tmp_path: Path,
    ):
        # 第一次跑：research/innovate 完成
        planner.build_plan(brief="测试", total_chapters=2, write_mode="sequential")
        planner.plan.tasks[0].status = TASK_DONE
        planner.plan.tasks[1].status = TASK_DONE
        planner.plan.save(planner.plan_path)

        # 新建 planner 模拟重启，加载已有清单后 run_all
        new_planner = TaskPlanner(
            mock_orchestrator, MagicMock(), planner.cfg, planner.worklog,
            plan_path=planner.plan_path,
        )
        new_planner.load_plan()
        await new_planner.run_all()

        # research/innovate 不应被再次调用
        mock_orchestrator.phase_research.assert_not_awaited()
        mock_orchestrator.phase_innovate.assert_not_awaited()
        # planning 应被调用
        mock_orchestrator.phase_planning.assert_awaited_once()
        # 所有任务最终都 done
        assert all(t.status == TASK_DONE for t in new_planner.plan.tasks)

    @pytest.mark.asyncio
    async def test_skips_skipped_tasks(self, planner: TaskPlanner, mock_orchestrator):
        planner.cfg.research_enabled = False
        planner.build_plan(brief="测试", total_chapters=2, write_mode="sequential")
        await planner.run_all()
        # research/innovate 被跳过，不应被调用
        mock_orchestrator.phase_research.assert_not_awaited()
        mock_orchestrator.phase_innovate.assert_not_awaited()
        # planning 应被调用
        mock_orchestrator.phase_planning.assert_awaited_once()
        # research/innovate 状态保持 skipped
        assert planner.plan.tasks[0].status == TASK_SKIPPED
        assert planner.plan.tasks[1].status == TASK_SKIPPED
