"""BatchCoordinator 测试：plan_batch JSON 解析容错、merge_gate PASS/REVISE 路径。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agents.worklog import WorkLog
from agents.coordinator import BatchCoordinator
from agents.knowledge import KnowledgeStore


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeAgent:
    """假 agent：按预设返回值回答 think()。"""

    def __init__(self, response: str, *, name="fake", role="Fake", model="fake-model"):
        self._response = response
        self.name = name
        self.role = role
        self.model = model
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        self.calls = 0

    async def think(self, prompt, context=None):
        self.calls += 1
        return self._response


def _build(tmp_path: Path, showrunner_resp: str, continuity_resp: str):
    kd = tmp_path / "knowledge"
    kd.mkdir(parents=True)
    ks = KnowledgeStore(str(kd))
    wl = WorkLog(kd / "story" / "agent_worklog.jsonl", job_id="job1")
    sr = _FakeAgent(showrunner_resp, name="showrunner", role="Showrunner")
    ck = _FakeAgent(continuity_resp, name="continuity_keeper", role="Continuity Keeper")

    class _Cfg:
        pass
    cfg = _Cfg()
    return BatchCoordinator(sr, ck, ks, cfg, wl, "job1"), sr, ck, ks, wl


# ── plan_batch ────────────────────────────────────────────────


def test_plan_batch_parses_valid_json(tmp_path: Path):
    """Showrunner 返回合法 JSON 时应解析为各章简报。"""
    raw = (
        '```json\n'
        '{"1": {"entry_state": "家中", "exit_state": "山道", '
        '"must_reveal": ["剑"], "must_not_reveal": ["身份"], "handoff": "剑碎"},'
        '"2": {"entry_state": "山道", "exit_state": "山巅"}}\n'
        '```'
    )
    coord, sr, ck, ks, wl = _build(tmp_path, raw, "")
    ks.save_outline("## 第 1 章 起\n## 第 2 章 承\n")
    batch_id, brief = _run(coord.plan_batch(1, 2))
    assert 1 in brief and 2 in brief
    assert brief[1]["entry_state"] == "家中"
    assert brief[2]["exit_state"] == "山巅"
    # 简报应持久化
    saved = ks.load_batch_brief(batch_id)
    assert saved["start"] == 1
    assert saved["count"] == 2
    # worklog 应记录 plan 动作
    entries = wl.read_recent(10)
    assert any(e["action"] == "plan" for e in entries)


def test_plan_batch_bad_json_degrades_to_empty(tmp_path: Path):
    """Showrunner 返回坏 JSON 时应退化为各章空 dict，不抛异常。"""
    coord, sr, ck, ks, wl = _build(tmp_path, "这不是JSON", "")
    ks.save_outline("## 第 1 章\n")
    batch_id, brief = _run(coord.plan_batch(1, 2))
    assert brief == {1: {}, 2: {}}


def test_plan_batch_llm_exception_degrades(tmp_path: Path):
    """LLM 调用异常时应退化空简报，不阻塞流程。"""

    class _BoomAgent(_FakeAgent):
        async def think(self, prompt, context=None):
            raise RuntimeError("API 挂了")

    kd = tmp_path / "knowledge"
    kd.mkdir(parents=True)
    ks = KnowledgeStore(str(kd))
    wl = WorkLog(kd / "story" / "agent_worklog.jsonl", job_id="job1")
    sr = _BoomAgent("")
    ck = _FakeAgent("")

    class _Cfg:
        pass
    coord = BatchCoordinator(sr, ck, ks, _Cfg(), wl, "job1")
    batch_id, brief = _run(coord.plan_batch(1, 3))
    assert brief == {1: {}, 2: {}, 3: {}}


# ── merge_gate ────────────────────────────────────────────────


def test_merge_gate_pass_returns_empty(tmp_path: Path):
    coord, sr, ck, ks, wl = _build(tmp_path, "", "VERDICT: PASS\n\n无冲突")
    ks.save_chapter(1, "第 1 章正文")
    ks.save_chapter(2, "第 2 章正文")
    conflicts = _run(coord.merge_gate([1, 2], batch_id="b1"))
    assert conflicts == {}
    # worklog 应记 verdict=PASS
    entries = wl.read_recent(10)
    merge_entries = [e for e in entries if e["action"] == "merge"]
    assert len(merge_entries) == 1
    assert merge_entries[0]["verdict"] == "PASS"


def test_merge_gate_revise_returns_conflicts(tmp_path: Path):
    raw = (
        'VERDICT: REVISE\n\n'
        '```json\n'
        '{"conflicts": [{"chapters": [1, 2], "issue": "时间线矛盾", "severity": "high"}]}\n'
        '```'
    )
    coord, sr, ck, ks, wl = _build(tmp_path, "", raw)
    ks.save_chapter(1, "第 1 章正文")
    ks.save_chapter(2, "第 2 章正文")
    conflicts = _run(coord.merge_gate([1, 2], batch_id="b1"))
    assert 1 in conflicts and 2 in conflicts
    assert "时间线矛盾" in conflicts[1][0]
    assert "时间线矛盾" in conflicts[2][0]


def test_merge_gate_empty_chapters_returns_empty(tmp_path: Path):
    coord, sr, ck, ks, wl = _build(tmp_path, "", "VERDICT: PASS")
    assert _run(coord.merge_gate([])) == {}


def test_merge_gate_exception_passes_through(tmp_path: Path):
    """LLM 异常时按无冲突放行，不阻塞。"""

    class _BoomAgent(_FakeAgent):
        async def think(self, prompt, context=None):
            raise RuntimeError("API 挂了")

    kd = tmp_path / "knowledge"
    kd.mkdir(parents=True)
    ks = KnowledgeStore(str(kd))
    wl = WorkLog(kd / "story" / "agent_worklog.jsonl", job_id="job1")
    sr = _FakeAgent("")
    ck = _BoomAgent("")

    class _Cfg:
        pass
    coord = BatchCoordinator(sr, ck, ks, _Cfg(), wl, "job1")
    ks.save_chapter(1, "x")
    assert _run(coord.merge_gate([1])) == {}


# ── JSON 解析辅助 ──────────────────────────────────────────────


def test_parse_json_block_code_fence():
    assert BatchCoordinator._parse_json_block('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_block_bare():
    assert BatchCoordinator._parse_json_block('前文 {"a": 2} 后文') == {"a": 2}


def test_parse_json_block_invalid_returns_none():
    assert BatchCoordinator._parse_json_block("not json at all") is None


def test_parse_verdict_pass():
    assert BatchCoordinator._parse_verdict("VERDICT: PASS\n") == "PASS"


def test_parse_verdict_default_revise():
    assert BatchCoordinator._parse_verdict("无格式输出") == "REVISE"
