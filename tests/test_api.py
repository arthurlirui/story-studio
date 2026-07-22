"""集成测试：FastAPI REST API 端点。

fastapi 未安装时整个文件 skip（api.py 是可选组件）。
用 TestClient 同步驱动，JobRunner 的 _run_job 被 monkeypatch 成假实现。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from config import StudioConfig
from jobs import JobRunner, JOB_SUCCEEDED, JOB_RUNNING


def _cfg(tmp_path: Path) -> StudioConfig:
    return StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
    )


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch):
    """构造一个 TestClient，JobRunner 用假 _run_job。"""
    # 假 _run_job：立即成功
    async def _fake_run_job(self, job, total_chapters):
        async with self._semaphore:
            job.status = "running"
            self._save_index()
            await asyncio.sleep(0.01)
            job.status = JOB_SUCCEEDED
            job.phase = "complete"
            job.result = {"total_chapters": total_chapters or 3, "preview": "完稿"}
            self._save_index()

    monkeypatch.setattr(JobRunner, "_run_job", _fake_run_job)

    # 临时设置 jobs dir 环境变量
    monkeypatch.setenv("STORY_STUDIO_JOBS_DIR", str(tmp_path / "jobs"))

    # 重置全局 runner
    import api
    api._runner = None
    # 让 load_config 用临时配置
    monkeypatch.setattr(api, "load_config", lambda: _cfg(tmp_path))

    with TestClient(api.app) as client:
        yield client

    api._runner = None


# ── Tests ────────────────────────────────────────────────────


def test_health(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_and_get_novel(app_client):
    resp = app_client.post("/novels", json={"brief": "剑客故事", "project_name": "剑客"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # 等后台任务跑完
    import time
    time.sleep(0.3)

    resp2 = app_client.get(f"/novels/{job_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["id"] == job_id
    assert data["status"] == JOB_SUCCEEDED


def test_list_novels(app_client):
    app_client.post("/novels", json={"brief": "故事1"})
    app_client.post("/novels", json={"brief": "故事2"})
    import time
    time.sleep(0.3)
    resp = app_client.get("/novels")
    assert resp.status_code == 200
    novels = resp.json()["novels"]
    assert len(novels) == 2


def test_get_nonexistent_novel_404(app_client):
    resp = app_client.get("/novels/nonexistent")
    assert resp.status_code == 404


def test_cancel_nonexistent_404(app_client):
    resp = app_client.delete("/novels/nonexistent")
    assert resp.status_code == 404


def test_get_chapter_404_when_missing(app_client):
    # 先创建一个 job
    resp = app_client.post("/novels", json={"brief": "故事"})
    job_id = resp.json()["job_id"]
    # 章节文件不存在
    resp2 = app_client.get(f"/novels/{job_id}/chapters/1")
    assert resp2.status_code == 404


# ── 任务端点测试（/tasks, /tasks/{n}/run, /run-all） ─────────


def _write_task_plan(job_id: str, tmp_path: Path):
    """直接写一份 task_plan.json 到 job 的 knowledge_dir，供 /tasks 读取。"""
    import json
    from planner import TaskPlan, Task

    plan = TaskPlan(job_id=job_id, brief="测试 brief", total_chapters=3, write_mode="sequential")
    plan.tasks = [
        Task(id=1, name="调研", phase="research", status="done"),
        Task(id=2, name="创新", phase="innovate", status="pending"),
        Task(id=3, name="策划", phase="planning", status="pending"),
    ]
    # 找到 job 的 knowledge_dir
    import api
    runner = api.get_runner()
    job = runner.get(job_id)
    plan_path = Path(job.knowledge_dir) / "task_plan.json"
    plan.save(plan_path)
    return plan


def test_get_tasks_no_plan(app_client):
    """无 task_plan.json 时 /tasks 返回 plan=null。"""
    resp = app_client.post("/novels", json={"brief": "故事"})
    job_id = resp.json()["job_id"]
    resp2 = app_client.get(f"/novels/{job_id}/tasks")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["plan"] is None


def test_get_tasks_returns_plan(app_client, tmp_path):
    """有 task_plan.json 时 /tasks 返回 plan 内容。"""
    resp = app_client.post("/novels", json={"brief": "故事"})
    job_id = resp.json()["job_id"]
    _write_task_plan(job_id, tmp_path)

    resp2 = app_client.get(f"/novels/{job_id}/tasks")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["plan"] is not None
    assert len(data["plan"]["tasks"]) == 3
    assert data["summary"]["done"] == 1


def test_run_task_updates_job_status(app_client, tmp_path, monkeypatch):
    """H4 修复：/tasks/{n}/run 应更新 job.status（running → succeeded/failed）。"""
    resp = app_client.post("/novels", json={"brief": "故事"})
    job_id = resp.json()["job_id"]
    _write_task_plan(job_id, tmp_path)

    # monkeypatch TaskPlanner.run_task 让它立即成功
    async def _fake_run_task(self, task):
        task.status = "done"
        return "task result"
    from planner import TaskPlanner
    monkeypatch.setattr(TaskPlanner, "run_task", _fake_run_task)

    resp2 = app_client.post(f"/novels/{job_id}/tasks/2/run")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "done"

    # job.status 应被更新为 succeeded
    import api
    job = api.get_runner().get(job_id)
    assert job.status == JOB_SUCCEEDED, f"H4 回归：job.status={job.status}（应 succeeded）"


def test_run_all_partial_failure(app_client, tmp_path, monkeypatch):
    """H6+H4 修复：/run-all 遇部分失败时返回 partial_failure 且 job 标记 failed。"""
    resp = app_client.post("/novels", json={"brief": "故事"})
    job_id = resp.json()["job_id"]
    _write_task_plan(job_id, tmp_path)

    # run_all 走真实 TaskPlanner 但 phase 抛异常 → summary.failed > 0
    async def _fake_run_all(self, on_progress=None, stop_on_failure=True):
        for t in self.plan.tasks:
            if t.phase == "innovate":
                t.status = "failed"
                t.error = "boom"
                if stop_on_failure:
                    break
            else:
                t.status = "done"
                if on_progress:
                    on_progress(t)
        return
    from planner import TaskPlanner
    monkeypatch.setattr(TaskPlanner, "run_all", _fake_run_all)

    resp2 = app_client.post(f"/novels/{job_id}/run-all")
    assert resp2.status_code == 200
    data = resp2.json()
    # H6: 部分失败应返回 partial_failure
    assert data["status"] == "partial_failure", f"H6 回归：status={data['status']}"
    # H4: job 应被标记 failed
    import api
    job = api.get_runner().get(job_id)
    assert job.status == "failed", f"H4 回归：job.status={job.status}（应 failed）"


def test_run_task_rejects_running_job(tmp_path: Path, monkeypatch):
    """job 仍 running 时 /tasks/{n}/run 应返回 409。

    用独立 fixture：_run_job 永远阻塞，确保 job 保持 running 状态。
    """
    async def _blocking_run_job(self, job, total_chapters):
        async with self._semaphore:
            job.status = JOB_RUNNING
            job.touch()
            self._save_index()
            await asyncio.sleep(100)  # 阻塞，保持 running

    monkeypatch.setattr(JobRunner, "_run_job", _blocking_run_job)
    monkeypatch.setenv("STORY_STUDIO_JOBS_DIR", str(tmp_path / "jobs"))
    import api
    api._runner = None
    monkeypatch.setattr(api, "load_config", lambda: _cfg(tmp_path))

    with TestClient(api.app) as client:
        resp = client.post("/novels", json={"brief": "故事"})
        job_id = resp.json()["job_id"]
        _write_task_plan(job_id, tmp_path)

        # 等 job 进入 running
        import time
        time.sleep(0.2)
        job = api.get_runner().get(job_id)
        assert job.status == JOB_RUNNING, f"setup 失败：job.status={job.status}"

        resp2 = client.post(f"/novels/{job_id}/tasks/2/run")
        assert resp2.status_code == 409

    api._runner = None
