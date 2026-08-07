"""
左侧控制面板 — 项目信息、创作设定、工作流控制、Agent 状态。
"""
from __future__ import annotations

from typing import Callable

import dearpygui.dearpygui as dpg

from gui.panels.menu import PHASE_LABELS, PHASE_ORDER, PHASE_IDLE

# ── 颜色定义 ──
COLOR_IDLE = (100, 100, 100)
COLOR_ACTIVE = (0, 120, 215)
COLOR_DONE = (0, 160, 80)
COLOR_ERROR = (200, 50, 50)

_WIDGET_TAG = "sidebar_panel"


# ── 公共 API ──

def build_sidebar(
    on_start: Callable,
    on_stop: Callable,
    on_phase_click: Callable,   # (phase_key: str)
    on_export: Callable,        # (export_type: str)
) -> None:
    """在左侧创建控制面板。

    应在主窗口布局创建后调用，使用 window 或 child 作为容器。
    """
    with dpg.child_window(tag=_WIDGET_TAG, width=260, autosize_x=False):
        _build_project_section()
        dpg.add_separator()
        _build_creation_section()
        dpg.add_separator()
        _build_workflow_section(on_start, on_stop, on_phase_click)
        dpg.add_separator()
        _build_actions_section(on_start, on_stop, on_export)
        dpg.add_separator()
        _build_agent_section()


# ── 更新函数（由 app.py 调用） ──

def update_phase_status(current_phase: str) -> None:
    """更新阶段状态指示器，反映当前进度。

    Args:
        current_phase: 当前所在阶段 key（如 "research"）
    """
    phase_index = PHASE_ORDER.index(current_phase) if current_phase in PHASE_ORDER else -1
    for i, pk in enumerate(PHASE_ORDER):
        status_tag = f"phase_status_{pk}"
        if not dpg.does_item_exist(status_tag):
            continue

        if i < phase_index:
            dpg.set_value(status_tag, "✅")
            dpg.configure_item(status_tag, color=COLOR_DONE)
        elif i == phase_index:
            dpg.set_value(status_tag, "▶")
            dpg.configure_item(status_tag, color=COLOR_ACTIVE)
        else:
            dpg.set_value(status_tag, "○")
            dpg.configure_item(status_tag, color=COLOR_IDLE)


def set_phase_error(phase_key: str) -> None:
    """标记某阶段为错误状态。"""
    status_tag = f"phase_status_{phase_key}"
    if dpg.does_item_exist(status_tag):
        dpg.set_value(status_tag, "❌")
        dpg.configure_item(status_tag, color=COLOR_ERROR)


def update_agent_status(agent_names: list[str]) -> None:
    """刷新 Agent 状态列表。"""
    tag = "agent_status_table"
    if not dpg.does_item_exist(tag):
        return

    # 清除旧行
    dpg.delete_item(tag, children_only=True)
    dpg.add_table_column(label="Agent", parent=tag)
    dpg.add_table_column(label="状态", parent=tag)

    for name in sorted(agent_names):
        with dpg.table_row(parent=tag):
            dpg.add_text(name)
            dpg.add_text("就绪", color=(100, 200, 100))


def get_brief_text() -> str:
    """获取梗概输入框的当前文本。"""
    tag = "input_brief"
    return dpg.get_value(tag) if dpg.does_item_exist(tag) else ""


def get_genre() -> str:
    """获取类型选择器的当前值。"""
    tag = "combo_genre"
    return dpg.get_value(tag) if dpg.does_item_exist(tag) else ""


def get_total_chapters() -> int:
    """获取章节数输入值。"""
    tag = "input_chapters"
    return dpg.get_value(tag) if dpg.does_item_exist(tag) else 10


def get_write_mode() -> str:
    """获取写作模式。"""
    tag = "combo_mode"
    return dpg.get_value(tag) if dpg.does_item_exist(tag) else "sequential"


# ── 内部构建函数 ──

def _build_project_section() -> None:
    """项目信息区。"""
    dpg.add_text("📁 项目信息", color=(180, 180, 100))
    dpg.add_input_text(
        tag="input_project_name",
        label="名称",
        default_value="",
        width=-1,
    )
    dpg.add_input_text(
        tag="input_author",
        label="作者",
        default_value="独孤元景 著",
        width=-1,
    )
    dpg.add_text(
        "knowledge_dir 从 settings.yaml 加载",
        tag="label_kd_path",
        color=(150, 150, 150),
    )


def _build_creation_section() -> None:
    """创作设定区。"""
    dpg.add_text("📝 创作设定", color=(180, 180, 100))

    dpg.add_input_text(
        tag="input_brief",
        label="梗概",
        default_value="",
        multiline=True,
        height=80,
        width=-1,
        hint="输入你的故事创意...",
    )

    dpg.add_combo(
        tag="combo_genre",
        label="类型",
        items=["", "都市高武", "古风世情", "古文虐恋"],
        default_value="",
        width=-1,
    )

    dpg.add_input_int(
        tag="input_chapters",
        label="章节数",
        default_value=10,
        min_value=1,
        max_value=200,
        width=-1,
    )

    dpg.add_combo(
        tag="combo_mode",
        label="写作模式",
        items=["sequential", "batch"],
        default_value="sequential",
        width=-1,
    )


def _build_workflow_section(
    on_start: Callable,
    on_stop: Callable,
    on_phase_click: Callable,
) -> None:
    """工作流控制区。"""
    dpg.add_text("🎬 工作流", color=(180, 180, 100))

    with dpg.group(horizontal=True):
        dpg.add_button(label="▶ 开始", callback=lambda: on_start(), width=80)
        dpg.add_button(label="⏹ 停止", callback=lambda: on_stop(), width=80)

    dpg.add_spacer(height=4)
    dpg.add_text("阶段进度:", color=(160, 160, 160))

    for i, pk in enumerate(PHASE_ORDER):
        label = PHASE_LABELS.get(pk, pk)
        with dpg.group(horizontal=True):
            dpg.add_text(
                tag=f"phase_status_{pk}",
                default_value="○",
                color=COLOR_IDLE,
            )
            dpg.add_button(
                tag=f"phase_btn_{pk}",
                label=f"{i+1}. {label}",
                callback=lambda s, a, u: on_phase_click(u),
                user_data=pk,
                width=-1,
                height=28,
            )


def _build_actions_section(
    on_start: Callable,
    on_stop: Callable,
    on_export: Callable,
) -> None:
    """操作按钮区。"""
    dpg.add_text("📦 操作", color=(180, 180, 100))
    with dpg.group(horizontal=True):
        dpg.add_button(label="📦 导出", callback=lambda: on_export("final"), width=75)
        # "保存全部" 按钮 — 回调通过 app.py 注册的外部回调注入
        dpg.add_button(label="💾 保存全部", tag="save_all_btn", width=75)


def _build_agent_section() -> None:
    """Agent 团队状态区。"""
    dpg.add_text("🤖 Agent 团队", color=(180, 180, 100))
    with dpg.table(
        tag="agent_status_table",
        header_row=True,
        borders_innerH=True,
        borders_outerH=True,
        borders_innerV=True,
        borders_outerV=True,
        height=200,
    ):
        dpg.add_table_column(label="Agent")
        dpg.add_table_column(label="状态")
    # 初始行在 update_agent_status() 中填充
