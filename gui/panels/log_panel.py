"""
底部日志面板 — 实时显示 Agent 输出、LLM 调用、工作流进度。
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Literal

import dearpygui.dearpygui as dpg

from gui.controller import GUILogEntry

# ── 常量 ──
WINDOW_TAG = "log_panel_window"
LOG_TEXT_TAG = "log_text_display"
MAX_LOG_LINES = 1000

FilterMode = Literal["all", "agent", "phase", "level"]


# ── 公共 API ──

def build_log_panel() -> None:
    """在底部创建日志面板。"""
    with dpg.child_window(tag=WINDOW_TAG, height=220, autosize_x=True):
        # 过滤栏
        with dpg.group(horizontal=True):
            dpg.add_text("🔍 过滤:")
            dpg.add_button(label="全部", callback=lambda: _set_filter("all"), width=50, tag="filter_btn_all")
            dpg.add_button(label="Agent", callback=lambda: _set_filter("agent"), width=50, tag="filter_btn_agent")
            dpg.add_button(label="阶段", callback=lambda: _set_filter("phase"), width=50, tag="filter_btn_phase")
            dpg.add_button(label="级别", callback=lambda: _set_filter("level"), width=50, tag="filter_btn_level")
            dpg.add_spacer(width=20)
            dpg.add_button(label="🗑 清除", callback=lambda: _clear_logs(), width=60)
            dpg.add_checkbox(label="自动滚动", default_value=True, tag="cb_auto_scroll")

        # 日志显示区
        with dpg.child_window(tag="log_container", height=-1, width=-1):
            dpg.add_text("", tag=LOG_TEXT_TAG, wrap=0)


# ── 日志追加 ──

def append_log(entry: GUILogEntry) -> None:
    """追加一条日志到面板（主线程安全）。

    日志按时间戳存储，超出 MAX_LOG_LINES 时丢弃旧条目。
    """
    if not dpg.does_item_exist(LOG_TEXT_TAG):
        return

    # 构建显示文本
    from datetime import datetime
    ts = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S")
    agent_str = f"[{entry.agent}]" if entry.agent else ""
    phase_str = f" ({entry.phase})" if entry.phase else ""

    # 颜色 emoji
    level_icon = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "SUCCESS": "✅"}.get(entry.level, "")

    line = f"{ts} {agent_str}{phase_str} {level_icon} {entry.message}"

    current = dpg.get_value(LOG_TEXT_TAG) or ""
    lines = current.split("\n") if current else []
    lines.append(line)

    # 裁剪
    if len(lines) > MAX_LOG_LINES:
        lines = lines[-MAX_LOG_LINES:]

    new_text = "\n".join(lines)
    dpg.set_value(LOG_TEXT_TAG, new_text)

    # 自动滚动到底部
    if dpg.get_value("cb_auto_scroll"):
        # DearPyGUI 没有直接的 scroll_to_bottom API，用 scroll_y 模拟
        try:
            dpg.set_y_scroll("log_container", 999999)
        except Exception:
            pass


# ── 内部 ──

def _set_filter(mode: FilterMode) -> None:
    """设置过滤模式（当前简化为全部显示，后续可扩展）。"""
    _ = mode  # 后续扩展
    # 高亮当前过滤按钮（用标签颜色代替 tint_color）
    for tag in ["filter_btn_all", "filter_btn_agent", "filter_btn_phase", "filter_btn_level"]:
        if dpg.does_item_exist(tag):
            if tag == f"filter_btn_{mode}":
                dpg.configure_item(tag, label=f"* {mode} *")
            else:
                _, _, rest = tag.partition("filter_btn_")
                dpg.configure_item(tag, label=rest)


def _clear_logs() -> None:
    """清空日志面板。"""
    if dpg.does_item_exist(LOG_TEXT_TAG):
        dpg.set_value(LOG_TEXT_TAG, "")
