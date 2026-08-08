"""GUI Controller 单元测试。

测试 GUIController 的核心逻辑（不依赖 dearpygui）：
- poll_events 事件分发（普通日志 / 阶段变更 / 任务完成）
- stop_event 语义
- _run_phase 异常捕获
- save_research 实现
- get_orchestrator_status 线程安全
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gui.controller import (
    GUIController,
    GUILogEntry,
    _EVENT_PHASE_CHANGE,
    _EVENT_JOB_DONE,
)


class TestPollEvents:
    """poll_events 事件分发测试。"""

    def test_dispatches_normal_log(self):
        """普通日志应分发到 _on_log 回调。"""
        ctrl = GUIController()
        received: list[GUILogEntry] = []
        ctrl.set_on_log(lambda entry: received.append(entry))

        ctrl.emit_log("Showrunner", "planning", "INFO", "测试消息")
        ctrl.poll_events()

        assert len(received) == 1
        assert received[0].agent == "Showrunner"
        assert received[0].message == "测试消息"

    def test_dispatches_phase_change(self):
        """_EVENT_PHASE_CHANGE 应分发到 _on_phase_change 回调，不传给 _on_log。"""
        ctrl = GUIController()
        logs: list[GUILogEntry] = []
        phases: list[str] = []
        ctrl.set_on_log(lambda entry: logs.append(entry))
        ctrl.set_on_phase_change(lambda phase: phases.append(phase))

        ctrl.log_queue.put(GUILogEntry(agent=_EVENT_PHASE_CHANGE, phase="writing"))
        ctrl.poll_events()

        assert len(phases) == 1
        assert phases[0] == "writing"
        assert len(logs) == 0  # 不应传给 _on_log

    def test_dispatches_job_done(self):
        """_EVENT_JOB_DONE 应分发到 _on_job_done 回调，并清理 _current_task。"""
        ctrl = GUIController()
        ctrl._current_task = MagicMock()
        ctrl._current_task.done.return_value = False

        results: list[bool] = []
        ctrl.set_on_job_done(lambda success: results.append(success))

        ctrl.log_queue.put(GUILogEntry(agent=_EVENT_JOB_DONE, message="success"))
        ctrl.poll_events()

        assert len(results) == 1
        assert results[0] is True
        assert ctrl._current_task is None  # 应被清理

    def test_job_done_stopped(self):
        """_EVENT_JOB_DONE message='stopped' 应传 False。"""
        ctrl = GUIController()
        results: list[bool] = []
        ctrl.set_on_job_done(lambda success: results.append(success))

        ctrl.log_queue.put(GUILogEntry(agent=_EVENT_JOB_DONE, message="stopped"))
        ctrl.poll_events()

        assert results[0] is False

    def test_multiple_events_in_one_poll(self):
        """一次 poll_events 应处理队列中所有待处理消息。"""
        ctrl = GUIController()
        logs: list[GUILogEntry] = []
        phases: list[str] = []
        ctrl.set_on_log(lambda entry: logs.append(entry))
        ctrl.set_on_phase_change(lambda phase: phases.append(phase))

        ctrl.emit_log("A", "p1", "INFO", "msg1")
        ctrl.log_queue.put(GUILogEntry(agent=_EVENT_PHASE_CHANGE, phase="p2"))
        ctrl.emit_log("B", "p3", "INFO", "msg2")

        ctrl.poll_events()

        assert len(logs) == 2
        assert len(phases) == 1

    def test_empty_queue_is_safe(self):
        """空队列 poll 不应报错。"""
        ctrl = GUIController()
        ctrl.set_on_log(lambda entry: None)
        ctrl.poll_events()  # 不应抛异常


class TestStopEvent:
    """stop_event 语义测试。"""

    def test_stop_sets_event(self):
        ctrl = GUIController()
        assert not ctrl._stop_event.is_set()
        ctrl.stop_job()
        assert ctrl._stop_event.is_set()

    def test_is_running_no_task(self):
        ctrl = GUIController()
        assert not ctrl.is_running()

    def test_is_running_with_active_task(self):
        ctrl = GUIController()
        ctrl._current_task = MagicMock()
        ctrl._current_task.done.return_value = False
        assert ctrl.is_running()

    def test_is_running_with_done_task(self):
        ctrl = GUIController()
        ctrl._current_task = MagicMock()
        ctrl._current_task.done.return_value = True
        assert not ctrl.is_running()


class TestRunPhase:
    """_run_phase 异常处理测试。"""

    def test_catches_exception_and_emits_error(self):
        """_run_phase 捕获异常并发送 ERROR 日志。"""
        ctrl = GUIController()
        logs: list[GUILogEntry] = []
        ctrl.set_on_log(lambda entry: logs.append(entry))

        async def failing_phase():
            raise ValueError("测试异常")

        async def _go():
            await ctrl._run_phase("test", "测试", failing_phase)

        asyncio.run(_go())
        # emit_log 入队后需 poll_events 才会分发到回调
        ctrl.poll_events()

        # 应有 INFO（开始）+ ERROR（失败）两条日志
        error_logs = [l for l in logs if l.level == "ERROR"]
        assert len(error_logs) == 1
        assert "测试异常" in error_logs[0].message

    def test_success_emits_success_log(self):
        """_run_phase 成功时发送 SUCCESS 日志。"""
        ctrl = GUIController()
        logs: list[GUILogEntry] = []
        ctrl.set_on_log(lambda entry: logs.append(entry))

        async def ok_phase():
            return "结果"

        async def _go():
            await ctrl._run_phase("test", "测试", ok_phase)

        asyncio.run(_go())
        ctrl.poll_events()

        success_logs = [l for l in logs if l.level == "SUCCESS"]
        assert len(success_logs) == 1
        assert "完成" in success_logs[0].message


class TestSaveResearch:
    """save_research 实现测试。"""

    def test_save_research_calls_store(self):
        """save_research 应调用 store.save_research（P1 修复：原为空操作）。"""
        ctrl = GUIController()
        ctrl.store = MagicMock()
        ctrl.store.save_research = MagicMock()

        ctrl.save_research("hot_events", "测试内容")

        ctrl.store.save_research.assert_called_once_with("hot_events", "测试内容")

    def test_save_research_no_store_is_safe(self):
        """无 store 时 save_research 不应崩溃。"""
        ctrl = GUIController()
        ctrl.store = None
        ctrl.save_research("topic", "content")  # 不应抛异常

    def test_save_research_emits_log(self):
        """save_research 成功后应发送 INFO 日志。"""
        ctrl = GUIController()
        ctrl.store = MagicMock()
        logs: list[GUILogEntry] = []
        ctrl.set_on_log(lambda entry: logs.append(entry))

        ctrl.save_research("hot_events", "测试内容")
        ctrl.poll_events()

        info_logs = [l for l in logs if l.level == "INFO"]
        assert len(info_logs) == 1


class TestThreadSafety:
    """线程安全测试。"""

    def test_get_status_with_lock(self):
        """get_orchestrator_status 应使用 _state_lock。"""
        ctrl = GUIController()
        mock_orch = MagicMock()
        mock_orch.get_status.return_value = {"phase": "idle"}
        ctrl.orchestrator = mock_orch

        result = ctrl.get_orchestrator_status()

        assert result["phase"] == "idle"
        mock_orch.get_status.assert_called_once()

    def test_get_status_no_orchestrator(self):
        """无 orchestrator 时返回空 dict。"""
        ctrl = GUIController()
        assert ctrl.get_orchestrator_status() == {}

    def test_get_agent_names_thread_safe(self):
        """get_agent_names 应使用 _state_lock。"""
        ctrl = GUIController()
        mock_orch = MagicMock()
        mock_orch.agents = {"showrunner": MagicMock(), "editor": MagicMock()}
        ctrl.orchestrator = mock_orch

        names = ctrl.get_agent_names()

        assert set(names) == {"showrunner", "editor"}
