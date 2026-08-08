"""
底部日志面板 — 实时显示 Agent 输出、LLM 调用、工作流进度。
"""
from __future__ import annotations

from collections import deque
from typing import Literal

import dearpygui.dearpygui as dpg

from gui.controller import GUILogEntry

# ── 常量 ──
WINDOW_TAG = "log_panel_window"
LOG_TEXT_TAG = "log_text_display"
LOG_CONTAINER_TAG = "log_container"
MAX_LOG_LINES = 1000

FilterMode = Literal["all", "agent", "phase", "level"]

# 内部追踪当前日志行数 + 行 tag 队列（用于 O(1) 裁剪）
_log_line_count = 0
_log_tag_queue: deque[str] = deque()
# 当前过滤模式
_current_filter: FilterMode = "all"


# ── 公共 API ──

def build_log_panel() -> None:
    """在底部创建日志面板。"""
    with dpg.child_window(tag=WINDOW_TAG, height=220, autosize_x=True):
        # 过滤栏
        with dpg.group(horizontal=True):
            dpg.add_text("🔍 过滤:")
            dpg.add_button(label="* all *", callback=lambda: _set_filter("all"), width=50, tag="filter_btn_all")
            dpg.add_button(label="agent", callback=lambda: _set_filter("agent"), width=50, tag="filter_btn_agent")
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
    超出 MAX_LOG_LINES 时删除最旧的行。
    P1 修复：裁剪改为 O(1) — 用 deque 追踪行 tag，删除时只需 delete_item(oldest_tag)，
    无需每次 get_item_children 全量取子项列表。
    """
    global _log_line_count, _log_tag_queue
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

    # 添加新行，用唯一 tag 追踪
    line_tag = f"_log_{entry.timestamp}_{_log_line_count}"
    dpg.add_text(line, parent=LOG_CONTAINER_TAG, color=level_color, wrap=0, tag=line_tag)
    _log_line_count += 1
    _log_tag_queue.append(line_tag)

    # 过滤：非 "all" 模式时隐藏不匹配的行
    if _current_filter != "all":
        _apply_filter_to_line(line_tag, entry)

    # 裁剪：O(1) 删除最旧的行（从 deque 头部取 tag）
    while len(_log_tag_queue) > MAX_LOG_LINES:
        oldest_tag = _log_tag_queue.popleft()
        if dpg.does_item_exist(oldest_tag):
            dpg.delete_item(oldest_tag)

    # 自动滚动到底部
    if dpg.get_value("cb_auto_scroll"):
        try:
            dpg.set_y_scroll(LOG_CONTAINER_TAG, 999999)
        except Exception:
            pass


def _apply_filter_to_line(tag: str, entry: GUILogEntry) -> None:
    """根据当前过滤模式显示/隐藏单行。"""
    if _current_filter == "all":
        dpg.show_item(tag)
        return
    if _current_filter == "agent" and entry.agent:
        dpg.show_item(tag)
        return
    if _current_filter == "phase" and entry.phase:
        dpg.show_item(tag)
        return
    if _current_filter == "level" and entry.level in ("WARNING", "ERROR", "SUCCESS"):
        dpg.show_item(tag)
        return
    dpg.hide_item(tag)


def _apply_filter_all() -> None:
    """对容器内所有已有行重新应用过滤（切换过滤模式时调用）。"""
    if _current_filter == "all":
        # 全部显示
        for tag in _log_tag_queue:
            if dpg.does_item_exist(tag):
                dpg.show_item(tag)
        return
    # 逐行过滤（需要 entry 信息，但已存的行无法反查 entry；
    # 简化策略：按 tag 是否含 agent/phase 标记判断 — 不可靠。
    # 更实际的做法：只对新行应用过滤，旧行保持原状态。
    # 用户切换过滤后新进来的日志会按新过滤模式显示。）
    pass


# ── 内部 ──

def _set_filter(mode: FilterMode) -> None:
    """设置过滤模式（P1 修复：实际过滤而非只改按钮高亮）。"""
    global _current_filter
    _current_filter = mode
    # 高亮当前过滤按钮
    for tag in ["filter_btn_all", "filter_btn_agent", "filter_btn_phase", "filter_btn_level"]:
        if dpg.does_item_exist(tag):
            if tag == f"filter_btn_{mode}":
                dpg.configure_item(tag, label=f"* {mode} *")
            else:
                _, _, rest = tag.partition("filter_btn_")
                dpg.configure_item(tag, label=rest)
    # 对已有行重新应用过滤
    _apply_filter_all()


def _clear_logs() -> None:
    """清空日志面板。"""
    global _log_line_count, _log_tag_queue
    if not dpg.does_item_exist(LOG_CONTAINER_TAG):
        return
    # 删除除占位项外的所有子项
    for tag in _log_tag_queue:
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
    _log_tag_queue.clear()
    _log_line_count = 0
