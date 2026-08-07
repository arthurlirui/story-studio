"""
对话框模块 — 新建 / 打开项目对话框、关于窗口。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import dearpygui.dearpygui as dpg

# 仓库根目录（dialogs.py → gui/panels/ → gui/ → repo root）
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def build_dialogs(
    on_new_confirm: Callable,   # (project_name: str, base_dir: str)
    on_open_confirm: Callable,  # (project_dir: str)
) -> None:
    """创建全局对话框窗口（初始隐藏）。

    Args:
        on_new_confirm: 新建项目确认回调
        on_open_confirm: 打开项目确认回调
    """
    # ── 关于窗口 ──
    with dpg.window(
        tag="about_window",
        label="关于 Story Studio",
        modal=True,
        show=False,
        width=400,
        height=250,
        no_resize=True,
    ):
        dpg.add_text("🎭 Story Studio", color=(200, 160, 60))
        dpg.add_text("v1.0.0")
        dpg.add_spacer(height=10)
        dpg.add_text("多 Agent 协作的 AI 小说创作平台")
        dpg.add_text("基于 DearPyGUI 的桌面创作工具")
        dpg.add_spacer(height=20)
        dpg.add_text("13 个专业 AI Agent 协作创作", color=(150, 150, 150))
        dpg.add_text("8 阶段完整工作流", color=(150, 150, 150))
        dpg.add_separator()
        dpg.add_button(label="关闭", callback=lambda: dpg.hide_item("about_window"), width=-1)

    # ── 新建项目对话框 ──
    with dpg.window(
        tag="new_project_dialog",
        label="📁 新建项目",
        modal=True,
        show=False,
        width=450,
        height=250,
        no_resize=True,
    ):
        dpg.add_input_text(
            tag="dialog_project_name",
            label="项目名称",
            default_value="新项目",
            width=-1,
        )
        dpg.add_input_text(
            tag="dialog_base_dir",
            label="保存路径",
            default_value=str(_REPO_ROOT / "projects"),
            width=-1,
        )

        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            dpg.add_button(label="取消", callback=lambda: dpg.hide_item("new_project_dialog"), width=100)
            dpg.add_button(
                label="✅ 创建",
                callback=lambda: _handle_new_confirm(on_new_confirm),
                width=100,
            )

    # ── 打开项目对话框 ──
    with dpg.window(
        tag="open_project_dialog",
        label="📂 打开项目",
        modal=True,
        show=False,
        width=450,
        height=200,
        no_resize=True,
    ):
        dpg.add_input_text(
            tag="dialog_open_dir",
            label="项目路径 (knowledge_dir)",
            default_value=str(_REPO_ROOT),
            width=-1,
        )
        dpg.add_text("提示: 选择包含 world/、characters/、story/ 的目录", color=(150, 150, 150))
        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            dpg.add_button(label="取消", callback=lambda: dpg.hide_item("open_project_dialog"), width=100)
            dpg.add_button(
                label="📂 打开",
                callback=lambda: _handle_open_confirm(on_open_confirm),
                width=100,
            )


def show_new_project_dialog() -> None:
    """显示新建项目对话框。"""
    dpg.show_item("new_project_dialog")


def show_open_project_dialog() -> None:
    """显示打开项目对话框。"""
    dpg.show_item("open_project_dialog")


# ── 内部 ──

def _handle_new_confirm(on_confirm: Callable) -> None:
    name = dpg.get_value("dialog_project_name")
    base_dir = dpg.get_value("dialog_base_dir")
    dpg.hide_item("new_project_dialog")
    on_confirm(name, base_dir)


def _handle_open_confirm(on_confirm: Callable) -> None:
    project_dir = dpg.get_value("dialog_open_dir")
    dpg.hide_item("open_project_dialog")
    on_confirm(project_dir)
