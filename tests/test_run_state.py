"""单元测试：orchestrator_state.RunState 的 save/load/merge/record_usage。

覆盖：
- save → load 往返一致性
- load 缺失/损坏文件返回 None
- merge_into_orchestrator 只在默认值时覆盖
- record_usage 按 model 分桶聚合 + None 跳过
- cost_summary 汇总
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


import pytest

from orchestrator_state import RunState, new_job_id, PHASE_IDLE, PHASE_WRITING


class TestSaveLoadRoundTrip:
    def test_save_then_load_preserves_fields(self, tmp_path: Path):
        state = RunState(
            job_id="job_123",
            project_name="测试小说",
            phase=PHASE_WRITING,
            current_chapter=5,
            total_chapters=20,
            created_at=1000.0,
            updated_at=2000.0,
            cost={"deepseek-v4": {"prompt_tokens": 100, "completion_tokens": 50,
                                  "total_tokens": 150, "calls": 2}},
        )
        path = tmp_path / "run_state.json"
        state.save(path)
        loaded = RunState.load(path)
        assert loaded is not None
        assert loaded.job_id == "job_123"
        assert loaded.project_name == "测试小说"
        assert loaded.phase == PHASE_WRITING
        assert loaded.current_chapter == 5
        assert loaded.total_chapters == 20
        assert loaded.created_at == 1000.0
        assert loaded.cost["deepseek-v4"]["total_tokens"] == 150
        assert loaded.cost["deepseek-v4"]["calls"] == 2

    def test_save_is_atomic(self, tmp_path: Path):
        """save 后不应残留 .tmp 文件。"""
        state = RunState(job_id="j1", project_name="x")
        path = tmp_path / "run_state.json"
        state.save(path)
        assert path.exists()
        assert not (tmp_path / "run_state.json.tmp").exists()

    def test_save_creates_parent_dir(self, tmp_path: Path):
        state = RunState(job_id="j1")
        path = tmp_path / "nested" / "dir" / "run_state.json"
        state.save(path)
        assert path.exists()

    def test_save_touches_updated_at(self, tmp_path: Path):
        state = RunState(job_id="j1", updated_at=100.0)
        before = time.time()
        path = tmp_path / "run_state.json"
        state.save(path)
        assert state.updated_at >= before


class TestLoadCorruption:
    def test_load_missing_file_returns_none(self, tmp_path: Path):
        assert RunState.load(tmp_path / "nope.json") is None

    def test_load_invalid_json_returns_none(self, tmp_path: Path):
        path = tmp_path / "run_state.json"
        path.write_text("not json {", encoding="utf-8")
        assert RunState.load(path) is None

    def test_load_missing_fields_uses_defaults(self, tmp_path: Path):
        path = tmp_path / "run_state.json"
        path.write_text(json.dumps({"job_id": "j1"}), encoding="utf-8")
        loaded = RunState.load(path)
        assert loaded is not None
        assert loaded.job_id == "j1"
        assert loaded.phase == PHASE_IDLE
        assert loaded.total_chapters == 0
        assert loaded.cost == {}


@dataclass
class FakeOrch:
    """模拟 orchestrator 的相关字段。"""
    project_name: str = ""
    phase: str = PHASE_IDLE
    total_chapters: int = 0
    current_chapter: int = 0
    job_id: str = ""
    run_cost: dict = field(default_factory=dict)


class TestMergeIntoOrchestrator:
    def test_merges_all_fields_when_orch_at_defaults(self):
        state = RunState(
            job_id="job_x",
            project_name="恢复的小说",
            phase=PHASE_WRITING,
            current_chapter=3,
            total_chapters=10,
            cost={"m": {"prompt_tokens": 1, "completion_tokens": 2,
                        "total_tokens": 3, "calls": 1}},
        )
        orch = FakeOrch()
        state.merge_into_orchestrator(orch)
        assert orch.job_id == "job_x"
        assert orch.project_name == "恢复的小说"
        assert orch.phase == PHASE_WRITING
        assert orch.total_chapters == 10
        assert orch.current_chapter == 3
        assert orch.run_cost["m"]["calls"] == 1

    def test_does_not_overwrite_non_default_orch_fields(self):
        """orch 已有 project_name/total_chapters 时不应被覆盖。"""
        state = RunState(
            job_id="job_x",
            project_name="盘上的",
            phase=PHASE_WRITING,
            total_chapters=99,
        )
        orch = FakeOrch(project_name="内存里的", total_chapters=5)
        state.merge_into_orchestrator(orch)
        assert orch.project_name == "内存里的"
        assert orch.total_chapters == 5
        # job_id 仍始终覆盖
        assert orch.job_id == "job_x"

    def test_job_id_always_overrides(self):
        """job_id 始终覆盖（即使 orch 已有）。"""
        state = RunState(job_id="persisted")
        orch = FakeOrch(job_id="fresh")
        state.merge_into_orchestrator(orch)
        assert orch.job_id == "persisted"


class TestRecordUsage:
    def test_aggregates_by_model(self):
        state = RunState(job_id="j1")
        state.record_usage("m1", {"prompt_tokens": 100, "completion_tokens": 50,
                                  "total_tokens": 150})
        state.record_usage("m1", {"prompt_tokens": 200, "completion_tokens": 10,
                                  "total_tokens": 210})
        state.record_usage("m2", {"prompt_tokens": 5, "completion_tokens": 5,
                                  "total_tokens": 10})
        assert state.cost["m1"]["prompt_tokens"] == 300
        assert state.cost["m1"]["completion_tokens"] == 60
        assert state.cost["m1"]["total_tokens"] == 360
        assert state.cost["m1"]["calls"] == 2
        assert state.cost["m2"]["calls"] == 1

    def test_none_usage_skipped(self):
        state = RunState(job_id="j1")
        state.record_usage("m1", None)
        assert state.cost == {}

    def test_empty_usage_skipped(self):
        """空字典被 falsy 守卫拦掉（与 None 一致），不创建桶。"""
        state = RunState(job_id="j1")
        state.record_usage("m1", {})
        assert state.cost == {}

    def test_cost_summary(self):
        state = RunState(job_id="j1")
        state.record_usage("m1", {"prompt_tokens": 100, "completion_tokens": 50,
                                  "total_tokens": 150})
        state.record_usage("m2", {"prompt_tokens": 10, "completion_tokens": 5,
                                  "total_tokens": 15})
        summary = state.cost_summary()
        assert summary["total_calls"] == 2
        assert summary["total_tokens"] == 165
        assert set(summary["by_model"].keys()) == {"m1", "m2"}


class TestNewJobId:
    def test_job_id_unique(self):
        ids = {new_job_id() for _ in range(100)}
        assert len(ids) == 100  # 全部唯一

    def test_job_id_format(self):
        jid = new_job_id()
        # 期望格式：<timestamp>_<8 hex>
        parts = jid.split("_")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert len(parts[1]) == 8
