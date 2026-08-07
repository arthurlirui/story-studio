"""
菜单栏模块 — 构建 DearPyGUI 主菜单栏。
"""
from __future__ import annotations

from typing import Callable

import dearpygui.dearpygui as dpg


# 阶段常量（与 orchestrator_state 保持一致）
PHASE_IDLE = "idle"
PHASE_RESEARCH = "research"
PHASE_INNOVATE = "innovate"
PHASE_PLANNING = "planning"
PHASE_BUILDING = "building"
PHASE_OUTLINING = "outlining"
PHASE_WRITING = "writing"
PHASE_COMPLETE = "complete"

PHASE_LABELS: dict[str, str] = {
    PHASE_IDLE: "空闲",
    PHASE_RESEARCH: "调研",
    PHASE_INNOVATE: "创新",
    PHASE_PLANNING: "企划",
    PHASE_BUILDING: "构建",
    PHASE_OUTLINING: "大纲",
    PHASE_WRITING: "写作",
    PHASE_COMPLETE: "完成",
}

PHASE_ORDER: list[str] = [
    PHASE_RESEARCH, PHASE_INNOVATE, PHASE_PLANNING,
    PHASE_BUILDING, PHASE_OUTLINING, PHASE_WRITING, PHASE_COMPLETE,
]


def build_menu_bar(
    on_new_project: Callable,
    on_open_project: Callable,
    on_save_all: Callable,
    on_export: Callable,
    on_start_pipeline: Callable,
    on_run_phase: Callable,
    on_stop: Callable,
    on_toggle_log: Callable,
) -> None:
    """创建并注册主菜单栏。

    Args:
        on_new_project: 新建项目回调
        on_open_project: 打开项目回调
        on_save_all: 保存全部回调
        on_export: 导出回调
        on_start_pipeline: 开始完整流程回调
        on_run_phase: 单独执行某阶段回调 (phase_key: str)
        on_stop: 停止任务回调
        on_toggle_log: 切换日志面板可见性回调
    """
    with dpg.viewport_menu_bar():
        # ── 文件 ──
        with dpg.menu(label="文件"):
            dpg.add_menu_item(label="📁 新建项目", callback=lambda: on_new_project())
            dpg.add_menu_item(label="📂 打开项目", callback=lambda: on_open_project())
            dpg.add_separator()
            dpg.add_menu_item(label="💾 保存全部", callback=lambda: on_save_all())
            dpg.add_separator()
            with dpg.menu(label="📦 导出"):
                dpg.add_menu_item(label="最终正文 (.txt)", callback=lambda: on_export("final"))
                dpg.add_menu_item(label="故事梗概", callback=lambda: on_export("synopsis"))
                dpg.add_menu_item(label="封面简报", callback=lambda: on_export("cover"))
            dpg.add_separator()
            dpg.add_menu_item(label="❌ 退出", callback=lambda: dpg.stop_dearpygui())

        # ── 运行 ──
        with dpg.menu(label="运行"):
            dpg.add_menu_item(label="▶ 完整流程", callback=lambda: on_start_pipeline())
            dpg.add_separator()
            with dpg.menu(label="单阶段执行"):
                for phase_key in PHASE_ORDER:
                    label = PHASE_LABELS.get(phase_key, phase_key)
                    dpg.add_menu_item(label=f"  {label}", callback=lambda p=phase_key: on_run_phase(p))
            dpg.add_separator()
            dpg.add_menu_item(label="⏹ 停止", callback=lambda: on_stop())

        # ── 视图 ──
        with dpg.menu(label="视图"):
            dpg.add_menu_item(label="📋 切换日志面板", callback=lambda: on_toggle_log())

        # ── 帮助 ──
        with dpg.menu(label="帮助"):
            dpg.add_menu_item(label="ℹ️ 关于 Story Studio", callback=lambda: dpg.show_item("about_window"))
