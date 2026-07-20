"""集成测试：JobRunner 的 submit → run → succeed / 并发 / cancel / index 持久化。

用 monkeypatch 替换 JobRunner._run_job 为可控的假实现，避免真实 LLM 调用。
所有测试在一个 event loop 里跑（后台 task 需要活着的 loop 才能执行）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


from config import StudioConfig
from jobs import JobRunner, JOB_SUCCEEDED, JOB_CANCELLED, JOB_RUNNING


def _cfg(tmp_path: Path) -> StudioConfig:
    return StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        main_model="test-main",
        light_model="test-light",
    )


@pytest.fixture
def fake_run_job(monkeypatch):
    """替换 _run_job 为最小状态机实现（不调真 LLM）。"""
    async def _minimal_run_job(self, job, total_chapters):
        async with self._semaphore:
            job.status = JOB_RUNNING
            job.touch()
            self._save_index()
            try:
                for phase in ("planning", "building", "outlining"):
                    job.phase = phase
                    job.touch()
                    self._save_index()
                    await asyncio.sleep(0.01)
                total = total_chapters or 3
                job.phase = "writing"
                job.progress = (0, total)
                self._save_index()
                for ch in range(1, total + 1):
                    await asyncio.sleep(0.01)
                    job.progress = (ch, total)
                    job.touch()
                    self._save_index()
                job.phase = "complete"
                job.status = JOB_SUCCEEDED
                job.result = {"total_chapters": total, "preview": "完稿"}
                job.touch()
                self._save_index()
            except asyncio.CancelledError:
                job.status = JOB_CANCELLED
                job.touch()
                self._save_index()
                raise

    monkeypatch.setattr(JobRunner, "_run_job", _minimal_run_job)


# ── Tests ────────────────────────────────────────────────────


async def _submit_and_wait(runner, brief="测试故事", project_name="测试",
                           total_chapters=2, wait=0.5):
    """提交 job 并等待其完成。"""
    job_id = await runner.submit(brief, project_name=project_name,
                                  total_chapters=total_chapters)
    await asyncio.sleep(wait)
    return job_id


def test_submit_then_succeed(tmp_path: Path, fake_run_job):
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path),
                           max_concurrent=2)
        job_id = await _submit_and_wait(runner, total_chapters=2, wait=0.5)
        job = runner.get(job_id)
        assert job is not None
        assert job.status == JOB_SUCCEEDED
        assert job.progress == (2, 2)
        assert job.phase == "complete"
        assert job.result["total_chapters"] == 2
    asyncio.run(_go())


def test_index_persisted(tmp_path: Path, fake_run_job):
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        job_id = await _submit_and_wait(runner, total_chapters=1, wait=0.3)

        index_path = tmp_path / "jobs" / "index.json"
        assert index_path.exists()
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert any(j["id"] == job_id for j in data["jobs"])

        # 重启 runner，应能读到 job
        runner2 = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        job = runner2.get(job_id)
        assert job is not None
        assert job.status == JOB_SUCCEEDED
    asyncio.run(_go())


def test_cancel_queued_job(tmp_path: Path, fake_run_job):
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path),
                           max_concurrent=1)  # 并发 1，第二个排队
        jid1 = await runner.submit("故事1", total_chapters=5)
        jid2 = await runner.submit("故事2", total_chapters=5)
        # jid2 应在排队（jid1 占着 semaphore）
        ok = await runner.cancel(jid2)
        assert ok
        job2 = runner.get(jid2)
        assert job2.status == JOB_CANCELLED
    asyncio.run(_go())


def test_list_returns_sorted(tmp_path: Path, fake_run_job):
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        jid1 = await runner.submit("故事1", total_chapters=1)
        jid2 = await runner.submit("故事2", total_chapters=1)
        jobs = runner.list()
        assert len(jobs) == 2
        # 最新的在前
        assert jobs[0].id == jid2
        assert jobs[1].id == jid1
    asyncio.run(_go())


def test_get_nonexistent_returns_none(tmp_path: Path, fake_run_job):
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        assert runner.get("nonexistent") is None
    asyncio.run(_go())


def test_cancel_nonexistent_returns_false(tmp_path: Path, fake_run_job):
    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path))
        assert await runner.cancel("nonexistent") is False
    asyncio.run(_go())


def test_concurrent_limit_respected(tmp_path: Path, monkeypatch):
    """max_concurrent=1 时，两个 job 不应同时 running。"""
    running_concurrent = [0]
    max_observed = [0]

    async def _tracking_run_job(self, job, total_chapters):
        async with self._semaphore:
            running_concurrent[0] += 1
            max_observed[0] = max(max_observed[0], running_concurrent[0])
            job.status = JOB_RUNNING
            self._save_index()
            await asyncio.sleep(0.2)
            running_concurrent[0] -= 1
            job.status = JOB_SUCCEEDED
            job.result = {"total_chapters": 1}
            self._save_index()

    monkeypatch.setattr(JobRunner, "_run_job", _tracking_run_job)

    async def _go():
        runner = JobRunner(base_dir=str(tmp_path / "jobs"), cfg=_cfg(tmp_path),
                           max_concurrent=1)
        await runner.submit("故事1", total_chapters=1)
        await runner.submit("故事2", total_chapters=1)
        await asyncio.sleep(0.6)
        assert max_observed[0] == 1  # 从不同时 running
    asyncio.run(_go())
