"""WorkLog 测试：JSONL append-only、并发安全、字段完整、读取过滤。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agents.worklog import WorkLog


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_append_writes_jsonl_line(tmp_path: Path):
    """单条 append 应写入一行合法 JSON。"""
    wl = WorkLog(tmp_path / "wl.jsonl", job_id="job1")
    _run(wl.append(action="write", agent="scene_writer_1", chapter=1, excerpt="hello"))
    lines = (tmp_path / "wl.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action"] == "write"
    assert entry["agent"] == "scene_writer_1"
    assert entry["chapter"] == 1
    assert entry["job_id"] == "job1"
    assert entry["excerpt"] == "hello"
    assert "ts" in entry


def test_excerpt_truncated(tmp_path: Path):
    """excerpt 超过 200 字应被截断。"""
    wl = WorkLog(tmp_path / "wl.jsonl")
    long_text = "x" * 500
    _run(wl.append(action="write", excerpt=long_text))
    entries = wl.read_recent(10)
    assert len(entries[0]["excerpt"]) == 200


def test_concurrent_appends_no_loss(tmp_path: Path):
    """并发 append 不应丢条目或撕裂行。"""
    wl = WorkLog(tmp_path / "wl.jsonl")

    async def many():
        await asyncio.gather(*[
            wl.append(action="write", agent=f"a{i}", chapter=i)
            for i in range(50)
        ])

    _run(many())
    lines = (tmp_path / "wl.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50
    # 每行都应是合法 JSON
    for line in lines:
        json.loads(line)


def test_read_recent_returns_last_n(tmp_path: Path):
    wl = WorkLog(tmp_path / "wl.jsonl")
    for i in range(10):
        _run(wl.append(action="write", chapter=i))
    recent = wl.read_recent(3)
    assert len(recent) == 3
    assert [e["chapter"] for e in recent] == [7, 8, 9]


def test_read_recent_empty_when_no_file(tmp_path: Path):
    wl = WorkLog(tmp_path / "missing.jsonl")
    assert wl.read_recent(10) == []
    assert wl.count() == 0


def test_read_recent_skips_malformed_lines(tmp_path: Path):
    """损坏行应被跳过，不影响其它行解析。"""
    wl = WorkLog(tmp_path / "wl.jsonl")
    _run(wl.append(action="write", chapter=1))
    # 手动追加一行坏数据
    with (tmp_path / "wl.jsonl").open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    _run(wl.append(action="write", chapter=2))
    entries = wl.read_recent(10)
    assert len(entries) == 2
    assert [e["chapter"] for e in entries] == [1, 2]


def test_count(tmp_path: Path):
    wl = WorkLog(tmp_path / "wl.jsonl")
    for i in range(5):
        _run(wl.append(action="write", chapter=i))
    assert wl.count() == 5
