"""
中央可编辑内容区 — 5 个 Tab（世界观 / 角色 / 大纲 / 章节 / 研究）。
"""
from __future__ import annotations

from typing import Callable

import dearpygui.dearpygui as dpg

# ── Tag 常量 ──
TAB_BAR_TAG = "editor_tab_bar"
EDITOR_TAG_WORLD = "tab_world_editor"
EDITOR_TAG_CHAR = "tab_char_editor"
EDITOR_TAG_OUTLINE = "tab_outline_editor"
EDITOR_TAG_CHAPTER = "tab_chapter_editor"
EDITOR_TAG_RESEARCH = "tab_research_editor"

CHAR_SELECTOR_TAG = "char_selector"
CHAPTER_SELECTOR_TAG = "chapter_selector"
RESEARCH_SELECTOR_TAG = "research_selector"


# ── 公共 API ──

def build_editor(
    on_save_world: Callable,
    on_save_char: Callable,
    on_save_outline: Callable,
    on_save_chapter: Callable,
    on_save_research: Callable,
    on_refresh_world: Callable,
    on_refresh_char: Callable,
    on_refresh_outline: Callable,
    on_refresh_chapter: Callable,
    on_refresh_research: Callable,
    on_char_select: Callable,       # (name: str)
    on_chapter_select: Callable,     # (num: int)
    on_research_select: Callable,    # (topic: str)
) -> None:
    """创建中央 Tab 栏编辑器区域。

    所有回调由 app.py 提供，负责从 controller 读写具体数据。
    """
    with dpg.tab_bar(tag=TAB_BAR_TAG):
        # ── Tab 1: 世界观 ──
        with dpg.tab(label="🌍 世界观"):
            dpg.add_input_text(
                tag=EDITOR_TAG_WORLD,
                multiline=True,
                width=-1,
                height=-1,
                tab_input=True,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="💾 保存", callback=lambda: on_save_world())
                dpg.add_button(label="🔄 刷新", callback=lambda: on_refresh_world())

        # ── Tab 2: 角色 ──
        with dpg.tab(label="👤 角色"):
            with dpg.group(horizontal=True):
                dpg.add_combo(
                    tag=CHAR_SELECTOR_TAG,
                    label="选择角色",
                    items=[],
                    width=200,
                    callback=lambda s, a, u: on_char_select(a),
                )
                dpg.add_button(label="🔄", callback=lambda: on_refresh_char(), width=30)
            dpg.add_input_text(
                tag=EDITOR_TAG_CHAR,
                multiline=True,
                width=-1,
                height=-1,
                tab_input=True,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="💾 保存角色", callback=lambda: on_save_char())

        # ── Tab 3: 大纲 ──
        with dpg.tab(label="📋 大纲"):
            dpg.add_input_text(
                tag=EDITOR_TAG_OUTLINE,
                multiline=True,
                width=-1,
                height=-1,
                tab_input=True,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="💾 保存", callback=lambda: on_save_outline())
                dpg.add_button(label="🔄 刷新", callback=lambda: on_refresh_outline())

        # ── Tab 4: 章节 ──
        with dpg.tab(label="📖 章节"):
            with dpg.group(horizontal=True):
                dpg.add_combo(
                    tag=CHAPTER_SELECTOR_TAG,
                    label="选择章节",
                    items=[],
                    width=200,
                    callback=lambda s, a, u: on_chapter_select(_safe_int(a, 1)),
                )
                dpg.add_button(label="🔄", callback=lambda: on_refresh_chapter(), width=30)
            dpg.add_input_text(
                tag=EDITOR_TAG_CHAPTER,
                multiline=True,
                width=-1,
                height=-1,
                tab_input=True,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="💾 保存章节", callback=lambda: on_save_chapter())

        # ── Tab 5: 研究 ──
        with dpg.tab(label="🔍 研究"):
            with dpg.group(horizontal=True):
                dpg.add_combo(
                    tag=RESEARCH_SELECTOR_TAG,
                    label="选择主题",
                    items=[],
                    width=200,
                    callback=lambda s, a, u: on_research_select(a),
                )
                dpg.add_button(label="🔄", callback=lambda: on_refresh_research(), width=30)
            dpg.add_input_text(
                tag=EDITOR_TAG_RESEARCH,
                multiline=True,
                width=-1,
                height=-1,
                tab_input=True,
            )
            dpg.add_button(label="💾 保存研究", callback=lambda: on_save_research())


# ── 更新函数 ──

def set_world_text(text: str) -> None:
    """设置世界观编辑器的文本。"""
    _safe_set_value(EDITOR_TAG_WORLD, text)


def get_world_text() -> str:
    """获取世界观编辑器当前文本。"""
    return _safe_get_value(EDITOR_TAG_WORLD)


def set_char_text(text: str) -> None:
    """设置角色编辑器的文本。"""
    _safe_set_value(EDITOR_TAG_CHAR, text)


def get_char_text() -> str:
    """获取角色编辑器当前文本。"""
    return _safe_get_value(EDITOR_TAG_CHAR)


def set_outline_text(text: str) -> None:
    """设置大纲编辑器的文本。"""
    _safe_set_value(EDITOR_TAG_OUTLINE, text)


def get_outline_text() -> str:
    """获取大纲编辑器当前文本。"""
    return _safe_get_value(EDITOR_TAG_OUTLINE)


def set_chapter_text(text: str) -> None:
    """设置章节编辑器的文本。"""
    _safe_set_value(EDITOR_TAG_CHAPTER, text)


def get_chapter_text() -> str:
    """获取章节编辑器当前文本。"""
    return _safe_get_value(EDITOR_TAG_CHAPTER)


def set_research_text(text: str) -> None:
    """设置研究编辑器的文本。"""
    _safe_set_value(EDITOR_TAG_RESEARCH, text)


def get_research_text() -> str:
    """获取研究编辑器当前文本。"""
    return _safe_get_value(EDITOR_TAG_RESEARCH)


def update_char_list(names: list[str]) -> None:
    """更新角色下拉列表。"""
    _safe_configure_item(CHAR_SELECTOR_TAG, items=names)
    if names:
        _safe_set_value(CHAR_SELECTOR_TAG, names[0])


def update_chapter_list(chapters: list[int]) -> None:
    """更新章节下拉列表。"""
    items = [str(c) for c in chapters]
    _safe_configure_item(CHAPTER_SELECTOR_TAG, items=items)
    if items:
        _safe_set_value(CHAPTER_SELECTOR_TAG, items[-1])


def update_research_list(topics: list[str]) -> None:
    """更新研究主题下拉列表。"""
    _safe_configure_item(RESEARCH_SELECTOR_TAG, items=topics)
    if topics:
        _safe_set_value(RESEARCH_SELECTOR_TAG, topics[0])


def get_selected_character() -> str:
    """获取当前选中的角色名。"""
    return _safe_get_value(CHAR_SELECTOR_TAG)


def get_selected_chapter() -> int:
    """获取当前选中的章节号。"""
    return _safe_int(_safe_get_value(CHAPTER_SELECTOR_TAG), 1)


def get_selected_research() -> str:
    """获取当前选中的研究主题。"""
    return _safe_get_value(RESEARCH_SELECTOR_TAG)


# ── 内部辅助 ──

def _safe_set_value(tag: str, value: str) -> None:
    if dpg.does_item_exist(tag):
        dpg.set_value(tag, value)


def _safe_get_value(tag: str) -> str:
    if dpg.does_item_exist(tag):
        return dpg.get_value(tag)
    return ""


def _safe_configure_item(tag: str, **kwargs) -> None:
    if dpg.does_item_exist(tag):
        dpg.configure_item(tag, **kwargs)


def _safe_int(val: str, default: int = 0) -> int:
    """安全将字符串转为 int，失败时返回 default。"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default
