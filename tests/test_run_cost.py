"""单元测试：RunCost 聚合 + get_status 暴露 cost_summary。

覆盖 Stage 3.2：
- _record_usage 按 agent.model 分桶聚合
- _record_usage 跳过 None / 空 usage
- get_status["cost"] 含 by_model / total_calls / total_tokens
- _cost_summary 汇总正确
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest


from config import StudioConfig
from orchestrator import StoryOrchestrator


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@dataclass
class FakeAgent:
    """模拟 agent，只暴露 last_usage 和 model。"""
    model: str
    last_usage: dict | None = None


@pytest.fixture
def orch(tmp_path: Path):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
    )
    # client=object() 足够，本测试不触发 LLM 调用
    return StoryOrchestrator(cfg, client=object())


class TestRecordUsage:
    def test_aggregates_by_model(self, orch: StoryOrchestrator):
        a1 = FakeAgent(model="m1", last_usage={"prompt_tokens": 100, "completion_tokens": 50,
                                               "total_tokens": 150})
        a2 = FakeAgent(model="m1", last_usage={"prompt_tokens": 200, "completion_tokens": 10,
                                               "total_tokens": 210})
        a3 = FakeAgent(model="m2", last_usage={"prompt_tokens": 5, "completion_tokens": 5,
                                               "total_tokens": 10})
        for a in (a1, a2, a3):
            orch._record_usage(a)
        assert orch.run_cost["m1"]["prompt_tokens"] == 300
        assert orch.run_cost["m1"]["total_tokens"] == 360
        assert orch.run_cost["m1"]["calls"] == 2
        assert orch.run_cost["m2"]["calls"] == 1

    def test_skips_none_usage(self, orch: StoryOrchestrator):
        orch._record_usage(FakeAgent(model="m1", last_usage=None))
        assert orch.run_cost == {}

    def test_skips_empty_usage(self, orch: StoryOrchestrator):
        orch._record_usage(FakeAgent(model="m1", last_usage={}))
        assert orch.run_cost == {}

    def test_handles_missing_last_usage_attr(self, orch: StoryOrchestrator):
        # 没有 last_usage 属性的 agent 不应崩溃
        class Bare:
            model = "m1"
        orch._record_usage(Bare())
        assert orch.run_cost == {}


class TestCostSummary:
    def test_summary_aggregates_across_models(self, orch: StoryOrchestrator):
        orch._record_usage(FakeAgent(model="m1", last_usage={"prompt_tokens": 100,
                                                             "completion_tokens": 50,
                                                             "total_tokens": 150}))
        orch._record_usage(FakeAgent(model="m2", last_usage={"prompt_tokens": 10,
                                                             "completion_tokens": 5,
                                                             "total_tokens": 15}))
        summary = orch._cost_summary()
        assert summary["total_calls"] == 2
        assert summary["total_tokens"] == 165
        assert set(summary["by_model"].keys()) == {"m1", "m2"}

    def test_summary_empty_when_no_usage(self, orch: StoryOrchestrator):
        summary = orch._cost_summary()
        assert summary["total_calls"] == 0
        assert summary["total_tokens"] == 0
        assert summary["by_model"] == {}

    def test_get_status_includes_cost(self, orch: StoryOrchestrator):
        orch._record_usage(FakeAgent(model="m1", last_usage={"prompt_tokens": 100,
                                                             "completion_tokens": 50,
                                                             "total_tokens": 150}))
        status = orch.get_status()
        assert "cost" in status
        assert status["cost"]["total_calls"] == 1
        assert status["cost"]["total_tokens"] == 150
        assert "m1" in status["cost"]["by_model"]
