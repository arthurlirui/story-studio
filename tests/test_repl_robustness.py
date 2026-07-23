"""单元测试：main.py 的 REPL 健壮性改动（Stage 1.5）。

覆盖：
- _parse_int：合法整数 / 非法输入不抛异常只打印用法
- _dispatch_command：/write abc、/review abc、/revise abc ... 不崩 REPL
- 命令异常被兜底 try/except 捕获
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock


import pytest

from main import _parse_int, _dispatch_command


# ── _parse_int ──────────────────────────────────────────────

class TestParseInt:
    def test_valid_int(self, capsys):
        assert _parse_int("42", "章节号") == 42
        out = capsys.readouterr().out
        assert "无效" not in out

    def test_invalid_str_returns_none(self, capsys):
        result = _parse_int("abc", "章节号")
        assert result is None
        out = capsys.readouterr().out
        assert "无效" in out
        assert "章节号" in out

    def test_empty_returns_none(self, capsys):
        assert _parse_int("", "章节号") is None

    def test_float_string_returns_none(self, capsys):
        # "3.5" 不是合法 int
        assert _parse_int("3.5", "章节号") is None

    def test_negative_valid(self, capsys):
        assert _parse_int("-1", "章节号") == -1


# ── _dispatch_command 不崩 REPL ──────────────────────────────

def _make_mock_orchestrator():
    """构造一个 mock orchestrator，避免触达真实 LLM/文件系统。"""
    orch = MagicMock()
    orch.get_status.return_value = {
        "project": "test",
        "phase": "writing",
        "chapters_written": 0,
        "total_chapters": 9,
        "world_docs": [],
        "characters": [],
        "agents": {},
    }
    # AsyncMock 替代已移除的 asyncio.coroutine（Python 3.12+）
    orch.phase_writing = AsyncMock(return_value="ok")
    orch.phase_building = AsyncMock(return_value="built")
    orch.phase_outlining = AsyncMock(return_value="outlined")
    orch.phase_complete = AsyncMock(return_value="completed")
    orch.chat_with_agent = AsyncMock(return_value="chatted")
    orch._team_discussion = AsyncMock(return_value="discussed")
    orch.current_chapter = 1
    orch.phase = "writing"
    orch.knowledge = MagicMock()
    orch.knowledge.load_chapter.return_value = ""
    return orch


class TestDispatchCommandRobustness:
    def test_write_with_non_numeric_does_not_crash(self, capsys):
        orch = _make_mock_orchestrator()
        # /write abc 不应抛 ValueError
        result = asyncio.run(_dispatch_command("/write abc", orch))
        assert result is False  # 不退出
        out = capsys.readouterr().out
        assert "无效" in out

    def test_review_with_non_numeric_does_not_crash(self, capsys):
        orch = _make_mock_orchestrator()
        result = asyncio.run(_dispatch_command("/review abc", orch))
        assert result is False
        out = capsys.readouterr().out
        assert "无效" in out

    def test_revise_with_non_numeric_does_not_crash(self, capsys):
        orch = _make_mock_orchestrator()
        result = asyncio.run(_dispatch_command("/revise abc make it longer", orch))
        assert result is False
        out = capsys.readouterr().out
        assert "无效" in out

    def test_exit_returns_true(self, capsys):
        orch = _make_mock_orchestrator()
        result = asyncio.run(_dispatch_command("/exit", orch))
        assert result is True

    def test_quit_returns_true(self, capsys):
        orch = _make_mock_orchestrator()
        result = asyncio.run(_dispatch_command("/quit", orch))
        assert result is True

    def test_help_does_not_crash(self, capsys):
        orch = _make_mock_orchestrator()
        result = asyncio.run(_dispatch_command("/help", orch))
        assert result is False
        out = capsys.readouterr().out
        assert "可用命令" in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
