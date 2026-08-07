"""
底部日志面板 — 实时显示 Agent 输出、LLM 调用、工作流进度。
"""
from __future__ import annotations

from typing import Literal

import dearpygui.dearpygui as dpg

from gui.controller import GUILogEntry

# ── 常量 ──
WINDOW_TAG = "log_panel_window"
LOG_TEXT_TAG = "log_text_display"
LOG_CONTAINER_TAG = "log_container"
MAX_LOG_LINES = 1000

FilterMode = Literal["all", "agent", "phase", "level"]

# 内部追踪当前日志行数，用于裁剪
_log_line_count = 0


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

        # 日志显示区 — 每行一个 dpg.add_text，避免全量 split/join
        with dpg.child_window(tag=LOG_CONTAINER_TAG, height=-1, width=-1):
            dpg.add_text("", tag=LOG_TEXT_TAG, wrap=0)  # 占位，实际行动态添加


# ── 日志追加 ──

def append_log(entry: GUILogEntry) -> None:
    """追加一条日志到面板（主线程安全）。

    每条日志作为独立的 dpg.add_text 添加到 log_container，
    超出 MAX_LOG_LINES 时删除最旧的行。避免全量 split/join 的 O(n²) 开销。
    """
    global _log_line_count
    if not dpg.does_item_exist(LOG_CONTAINER_TAG):
        return

    # 构建显示文本
    from datetime import datetime
    ts = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S")
    agent_str = f"[{entry.agent}]" if entry.agent else ""
    phase_str = f" ({entry.phase})" if entry.phase else ""

    # 级别颜色
    level_color = {
        "INFO": (200, 200, 200),
        "WARNING": (220, 180, 60),
        "ERROR": (220, 80, 80),
        "SUCCESS": (80, 200, 100),
    }.get(entry.level, (200, 200, 200))
    level_icon = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "SUCCESS": "✅"}.get(entry.level, "")

    line = f"{ts} {agent_str}{phase_str} {level_icon} {entry.message}"

    # 添加新行
    dpg.add_text(line, parent=LOG_CONTAINER_TAG, color=level_color, wrap=0)
    _log_line_count += 1

    # 裁剪：删除最旧的行（容器中第一个子项是占位文本，跳过）
    while _log_line_count > MAX_LOG_LINES:
        children = dpg.get_item_children(LOG_CONTAINER_TAG, 1)
        if not children or len(children) <= 1:
            break
        # 删除第二个子项（第一个是占位 LOG_TEXT_TAG）
        dpg.delete_item(children[1])
        _log_line_count -= 1

    # 自动滚动到底部
    if dpg.get_value("cb_auto_scroll"):
        try:
            dpg.set_y_scroll(LOG_CONTAINER_TAG, 999999)
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
    global _log_line_count
    if not dpg.does_item_exist(LOG_CONTAINER_TAG):
        return
    # 删除除占位项外的所有子项
    children = dpg.get_item_children(LOG_CONTAINER_TAG, 1) or []
    for child in children[1:]:  # 跳过第一个占位文本
        dpg.delete_item(child)
    _log_line_count = 0
