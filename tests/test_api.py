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
from jobs import JobRunner, JOB_SUCCEEDED


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
