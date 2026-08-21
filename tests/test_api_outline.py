"""大纲结构化端点测试：GET /outline/structured + PUT /outline。

沿用 test_api.py 的 TestClient + 假 _run_job 模式。
"""
from __future__ import annotations

import asyncio
import json
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
    async def _fake_run_job(self, job, total_chapters):
        async with self._semaphore:
            job.status = JOB_SUCCEEDED
            job.phase = "complete"
            self._save_index()

    monkeypatch.setattr(JobRunner, "_run_job", _fake_run_job)
    monkeypatch.setenv("STORY_STUDIO_JOBS_DIR", str(tmp_path / "jobs"))

    import api
    api._runner = None
    monkeypatch.setattr(api, "load_config", lambda: _cfg(tmp_path))

    with TestClient(api.app) as client:
        yield client

    api._runner = None


def _new_job(client) -> str:
    resp = client.post("/novels", json={"brief": "测试故事"})
    assert resp.status_code == 200
    return resp.json()["job_id"]


# ── GET /outline/structured ──────────────────────────────────


def test_get_structured_empty_outline(app_client):
    job_id = _new_job(client := app_client)
    resp = client.get(f"/novels/{job_id}/outline/structured")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chapters"] == []
    assert data["book_title"] == ""
    assert data["preamble"] == ""


def test_get_structured_404(app_client):
    assert app_client.get("/novels/nonexistent/outline/structured").status_code == 404


def test_get_structured_parses_existing_outline(app_client):
    job_id = _new_job(app_client)
    import api
    kd = Path(api.get_runner().get(job_id).knowledge_dir)
    (kd / "story").mkdir(parents=True, exist_ok=True)
    (kd / "story" / "outline.md").write_text(
        "## 第1章：开局\n\n*   **核心事件**：\n    1.  事件A\n"
        "*   **出场角色**：张三、李四\n*   **字数预估**：2000字\n",
        encoding="utf-8",
    )
    resp = app_client.get(f"/novels/{job_id}/outline/structured")
    data = resp.json()
    assert len(data["chapters"]) == 1
    ch = data["chapters"][0]
    assert ch["title"] == "开局"
    assert ch["events"] == ["事件A"]
    assert ch["characters"] == ["张三", "李四"]
    assert ch["word_estimate"] == 2000


# ── PUT /outline ─────────────────────────────────────────────


def test_put_structured_saves_and_roundtrips(app_client):
    client = app_client
    job_id = _new_job(client)
    payload = {
        "structured": {
            "book_title": "测试书",
            "preamble": "节奏紧凑。",
            "chapters": [
                {
                    "num": 1,
                    "title": "开局",
                    "events": ["事件A", "事件B"],
                    "characters": ["张三"],
                    "hook": "悬念",
                    "word_estimate": 2000,
                },
                {
                    "num": 7,  # 乱序章号应被服务端重排为 2
                    "title": "转折",
                    "events": [],
                    "characters": [],
                    "hook": "",
                    "word_estimate": 3000,
                },
            ],
        }
    }
    resp = client.put(f"/novels/{job_id}/outline", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["saved"] is True
    assert data["parsed_chapters"] == 2
    assert data["total_chapters"] == 2

    # 结构化读回应与保存内容一致（章号已重排）
    got = client.get(f"/novels/{job_id}/outline/structured").json()
    assert got["book_title"] == "测试书"
    assert got["preamble"] == "节奏紧凑。"
    assert [c["num"] for c in got["chapters"]] == [1, 2]
    assert got["chapters"][0]["events"] == ["事件A", "事件B"]
    assert got["chapters"][1]["title"] == "转折"

    # 原文读回：渲染格式能被写作流水线解析
    raw = client.get(f"/novels/{job_id}/outline").json()["outline"]
    from agents.utils import extract_chapter_outline
    assert "开局" in extract_chapter_outline(raw, 1)
    assert "转折" in extract_chapter_outline(raw, 2)


def test_put_raw_markdown(app_client):
    client = app_client
    job_id = _new_job(client)
    md = "## 第1章：原始\n\n*   **出场角色**：张三\n"
    resp = client.put(f"/novels/{job_id}/outline", json={"outline": md})
    assert resp.status_code == 200
    assert client.get(f"/novels/{job_id}/outline").json()["outline"] == md


def test_put_requires_body_field(app_client):
    job_id = _new_job(app_client)
    resp = app_client.put(f"/novels/{job_id}/outline", json={})
    assert resp.status_code == 422


def test_put_404(app_client):
    resp = app_client.put("/novels/nonexistent/outline", json={"outline": "x"})
    assert resp.status_code == 404


def test_put_syncs_run_state_total_chapters(app_client):
    client = app_client
    job_id = _new_job(client)
    import api
    kd = Path(api.get_runner().get(job_id).knowledge_dir)
    kd.mkdir(parents=True, exist_ok=True)
    (kd / "run_state.json").write_text(
        json.dumps({"job_id": job_id, "total_chapters": 10, "phase": "outlining"}),
        encoding="utf-8",
    )

    payload = {
        "structured": {
            "book_title": "",
            "preamble": "",
            "chapters": [
                {"num": 1, "title": "一", "events": [], "characters": [], "hook": "", "word_estimate": 2000},
                {"num": 2, "title": "二", "events": [], "characters": [], "hook": "", "word_estimate": 2000},
                {"num": 3, "title": "三", "events": [], "characters": [], "hook": "", "word_estimate": 2000},
            ],
        }
    }
    resp = client.put(f"/novels/{job_id}/outline", json=payload)
    assert resp.json()["total_chapters"] == 3

    state = json.loads((kd / "run_state.json").read_text(encoding="utf-8"))
    assert state["total_chapters"] == 3
    assert state["job_id"] == job_id  # 其余字段不被破坏
