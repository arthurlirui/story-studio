"""
Story Studio DearPyGUI 桌面应用入口。

启动: python -m gui.app  或  ss-gui  或  ss gui

布局:
┌──────────────────────────────────────────────────────────┐
│ 菜单栏: 文件 | 运行 | 视图 | 帮助                         │
├───────────┬──────────────────────────────────────────────┤
│ 左侧面板   │ 中央内容区（5 Tab 编辑器）                     │
│ (260px)   │                                              │
│           ├──────────────────────────────────────────────┤
│           │ 日志面板 (220px)                              │
└───────────┴──────────────────────────────────────────────┘
"""
from __future__ import annotations

import time
from pathlib import Path

import dearpygui.dearpygui as dpg

from gui.controller import GUIController, GUILogEntry
from gui.panels import menu, sidebar, editor, log_panel, dialogs

# ── 常量 ──
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900
LOG_POLL_INTERVAL = 0.05  # 50ms — 日志轮询最小间隔，避免高帧率下空轮询


# ── 全局控制器实例 ──
_ctrl = GUIController()
_last_poll_time = 0.0


# ======================================================================
# 主入口
# ======================================================================

def main() -> None:
    """启动 DearPyGUI 桌面应用。"""
    # 1. 创建上下文和视口
    dpg.create_context()

    # 2. 初始化控制器（加载配置）
    _init_project()

    # 3. 构建 UI
    _build_ui()

    # 4. 创建视口
    dpg.create_viewport(
        title="🎭 Story Studio — AI 小说创作工作台",
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_width=1024,
        min_height=600,
    )

    # 5. 设置视口 resize 回调
    dpg.set_viewport_resize_callback(_on_viewport_resize)

    # 6. 设置 DearPyGUI
    dpg.setup_dearpygui()

    # 7. 显示窗口 + 调整主窗口大小
    dpg.show_viewport()
    dpg.maximize_viewport()

    # 8. 渲染循环
    while dpg.is_dearpygui_running():
        # 每帧轮询日志队列（限流到 LOG_POLL_INTERVAL）
        _poll_logs()
        dpg.render_dearpygui_frame()

    # 9. 清理
    dpg.destroy_context()


# ======================================================================
# 项目初始化
# ======================================================================

def _init_project() -> None:
    """加载配置，初始化 orchestrator 和 knowledge store。"""
    success = _ctrl.init_project()
    if success and _ctrl.orchestrator:
        _ctrl.emit_log("System", "", "SUCCESS", "✅ 项目初始化成功")
    elif success:
        _ctrl.emit_log("System", "", "WARNING", "⚠️ 项目以只读模式运行（未配置 API key）")


# ======================================================================
# UI 构建
# ======================================================================

def _build_ui() -> None:
    """构建完整的 GUI 布局。"""
    # ── 菜单栏 ──
    _build_menus()

    # ── 对话框 ──
    dialogs.build_dialogs(
        on_new_confirm=_on_new_project,
        on_open_confirm=_on_open_project,
    )

    # ── 主布局（包裹在 primary window 中）──
    with dpg.window(
        tag="primary_window",
        no_title_bar=True,
        no_move=True,
        no_resize=True,
        no_close=True,
        no_collapse=True,
        no_scrollbar=True,
    ):
        with dpg.group(horizontal=True):
            # 左侧面板
            sidebar.build_sidebar(
                on_start=_on_start_pipeline,
                on_stop=_on_stop,
                on_phase_click=_on_run_single_phase,
                on_export=_on_export,
                on_save_all=_on_save_all,
            )

            # 右侧区域（上下分）
            with dpg.group():
                # 上半: 编辑器 Tab 区
                with dpg.child_window(tag="editor_area", height=-220, width=-1):
                    editor.build_editor(
                        on_save_world=_on_save_world,
                        on_save_char=_on_save_char,
                        on_save_outline=_on_save_outline,
                        on_save_chapter=_on_save_chapter,
                        on_save_research=_on_save_research,
                        on_refresh_world=_on_refresh_world,
                        on_refresh_char=_on_refresh_char,
                        on_refresh_outline=_on_refresh_outline,
                        on_refresh_chapter=_on_refresh_chapter,
                        on_refresh_research=_on_refresh_research,
                        on_char_select=_on_char_select,
                        on_chapter_select=_on_chapter_select,
                        on_research_select=_on_research_select,
                    )

                # 下半: 日志面板
                log_panel.build_log_panel()

    # ── 注册控制器回调 ──
    _ctrl.set_on_log(_handle_log_entry)
    _ctrl.set_on_phase_change(_on_phase_change_from_job)
    _ctrl.set_on_job_done(_on_job_done)

    # ── 初始刷新编辑器内容 ──
    _refresh_all_editors()


def _build_menus() -> None:
    """构建菜单栏并连接回调。"""
    menu.build_menu_bar(
        on_new_project=lambda: dialogs.show_new_project_dialog(),
        on_open_project=lambda: dialogs.show_open_project_dialog(),
        on_save_all=lambda: _on_save_all(),
        on_export=lambda t: _on_export(t),
        on_start_pipeline=lambda: _on_start_pipeline(),
        on_run_phase=lambda p: _on_run_single_phase(p),
        on_stop=lambda: _on_stop(),
        on_toggle_log=lambda: _on_toggle_log(),
    )


# ======================================================================
# 回调: 项目操作
# ======================================================================

def _on_new_project(name: str, base_dir: str) -> None:
    """新建项目：创建目录结构并重新初始化。"""
    project_dir = Path(base_dir) / name
    project_dir.mkdir(parents=True, exist_ok=True)
    kd = project_dir / "knowledge"

    # 创建知识库子目录
    for sub in ["world", "characters", "story/chapters", "story/revisions",
                "story/summaries", "story/reviews", "research"]:
        (kd / sub).mkdir(parents=True, exist_ok=True)

    # 更新 config 并重建
    if _ctrl.config:
        _ctrl.config.knowledge_dir = str(kd)
        _ctrl.config.output_dir = str(project_dir / "output")
    _ctrl.init_project()

    dpg.set_value("label_kd_path", f"📂 {kd}")
    dpg.set_value("input_project_name", name)
    _ctrl.emit_log("System", "", "SUCCESS", f"✅ 项目 [{name}] 已创建: {kd}")
    _refresh_all_editors()


def _on_open_project(project_dir: str) -> None:
    """打开已有项目。"""
    p = Path(project_dir)
    if not p.exists():
        _ctrl.emit_log("System", "", "ERROR", f"路径不存在: {project_dir}")
        return

    kd = p if (p / "world").exists() else p / "knowledge"
    if not (kd / "world").exists():
        _ctrl.emit_log("System", "", "ERROR", f"非有效项目目录（缺少 world/ 子目录）: {kd}")
        return

    if _ctrl.config:
        _ctrl.config.knowledge_dir = str(kd)
        _ctrl.config.output_dir = str(p / "output")
    _ctrl.init_project()

    dpg.set_value("label_kd_path", f"📂 {kd}")
    dpg.set_value("input_project_name", p.name)
    _ctrl.emit_log("System", "", "SUCCESS", f"✅ 已打开项目: {kd}")
    _refresh_all_editors()


# ======================================================================
# 回调: 工作流控制
# ======================================================================

def _on_start_pipeline() -> None:
    """开始完整创作流程。"""
    brief = sidebar.get_brief_text().strip()
    if not brief:
        _ctrl.emit_log("System", "", "WARNING", "⚠️ 请先输入故事梗概")
        return

    genre = sidebar.get_genre()
    chapters = sidebar.get_total_chapters()
    mode = sidebar.get_write_mode()

    _ctrl.emit_log("System", "", "INFO",
                    f"📝 梗概: {brief[:80]}... | 类型: {genre or '未指定'} | "
                    f"{chapters}章 | 模式: {mode}")
    _ctrl.start_full_pipeline(brief, genre, chapters, mode)


def _on_run_single_phase(phase_key: str) -> None:
    """单独运行某个阶段，传入当前梗概供 research/innovate/planning 使用。"""
    brief = sidebar.get_brief_text().strip()
    _ctrl.start_single_phase(phase_key, brief=brief)


def _on_stop() -> None:
    """停止当前后台任务。"""
    _ctrl.stop_job()


# ======================================================================
# 回调: 编辑器操作
# ======================================================================

def _on_save_world() -> None:
    _ctrl.save_world_settings(editor.get_world_text())


def _on_save_char() -> None:
    name = editor.get_selected_character()
    if name:
        _ctrl.save_character(name, editor.get_char_text())


def _on_save_outline() -> None:
    _ctrl.save_outline(editor.get_outline_text())


def _on_save_chapter() -> None:
    num = editor.get_selected_chapter()
    if num > 0:
        author = dpg.get_value("input_author") if dpg.does_item_exist("input_author") else ""
        _ctrl.save_chapter(num, editor.get_chapter_text(), author)


def _on_save_research() -> None:
    topic = editor.get_selected_research()
    if topic:
        _ctrl.emit_log("System", "", "INFO", f"💾 研究 [{topic}] 保存（需实现 save_research）")


def _on_save_all() -> None:
    """保存所有编辑器内容。"""
    _on_save_world()
    _on_save_char()
    _on_save_outline()
    _on_save_chapter()
    _on_save_research()
    _ctrl.emit_log("System", "", "SUCCESS", "✅ 全部内容已保存")


# ── 刷新 ──

def _on_refresh_world() -> None:
    editor.set_world_text(_ctrl.load_world_settings())
    _ctrl.emit_log("System", "", "INFO", "🔄 世界观已刷新")


def _on_refresh_char() -> None:
    chars = _ctrl.list_characters()
    editor.update_char_list(chars)
    if chars:
        editor.set_char_text(_ctrl.load_character(chars[0]))
        dpg.set_value(editor.CHAR_SELECTOR_TAG, chars[0])
    else:
        editor.set_char_text("")
    _ctrl.emit_log("System", "", "INFO", f"🔄 角色列表已刷新 ({len(chars)} 个)")


def _on_refresh_outline() -> None:
    editor.set_outline_text(_ctrl.load_outline())
    _ctrl.emit_log("System", "", "INFO", "🔄 大纲已刷新")


def _on_refresh_chapter() -> None:
    chapters = _ctrl.list_chapters()
    editor.update_chapter_list(chapters)
    if chapters:
        editor.set_chapter_text(_ctrl.load_chapter(chapters[-1]))
        dpg.set_value(editor.CHAPTER_SELECTOR_TAG, str(chapters[-1]))
    else:
        editor.set_chapter_text("")
    _ctrl.emit_log("System", "", "INFO", f"🔄 章节列表已刷新 ({len(chapters)} 章)")


def _on_refresh_research() -> None:
    topics = _ctrl.list_research_topics()
    editor.update_research_list(topics)
    if topics:
        editor.set_research_text(_ctrl.load_research(topics[0]))
        dpg.set_value(editor.RESEARCH_SELECTOR_TAG, topics[0])
    else:
        editor.set_research_text("")
    _ctrl.emit_log("System", "", "INFO", f"🔄 研究主题已刷新 ({len(topics)} 个)")


def _refresh_all_editors() -> None:
    """启动时刷新所有编辑器内容。"""
    _on_refresh_world()
    _on_refresh_char()
    _on_refresh_outline()
    _on_refresh_chapter()
    _on_refresh_research()

    # 更新知识库路径显示
    if _ctrl.config and hasattr(_ctrl.config, 'knowledge_dir') and _ctrl.config.knowledge_dir:
        if dpg.does_item_exist("label_kd_path"):
            dpg.set_value("label_kd_path", f"📂 {_ctrl.config.knowledge_dir}")

    # 刷新 Agent 列表
    agents = _ctrl.get_agent_names()
    sidebar.update_agent_status(agents)

    # 刷新当前阶段
    status = _ctrl.get_orchestrator_status()
    current_phase = status.get("phase", "idle") if status else "idle"
    sidebar.update_phase_status(current_phase)


# ── 选择器变更 ──

def _on_char_select(name: str) -> None:
    if name:
        editor.set_char_text(_ctrl.load_character(name))


def _on_chapter_select(num: int) -> None:
    if num > 0:
        editor.set_chapter_text(_ctrl.load_chapter(num))


def _on_research_select(topic: str) -> None:
    if topic:
        editor.set_research_text(_ctrl.load_research(topic))


# ======================================================================
# 回调: 导出
# ======================================================================

def _on_export(export_type: str) -> None:
    """导出成品文件。

    Args:
        export_type: "final" | "synopsis" | "cover"
    """
    if not _ctrl.config:
        _ctrl.emit_log("System", "", "ERROR", "未初始化配置，无法导出")
        return

    out_dir = Path(_ctrl.config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        if export_type == "final":
            # 尝试读取已生成的文件
            final_md = out_dir / "final.md"
            final_txt = out_dir / "final.txt"
            if final_txt.exists():
                _ctrl.emit_log("System", "", "SUCCESS",
                                f"📦 最终正文已存在: {final_txt}")
            elif final_md.exists():
                _ctrl.emit_log("System", "", "SUCCESS",
                                f"📦 最终正文 (md) 已存在: {final_md}")
            else:
                # 拼接所有章节为导出内容
                chapters = _ctrl.list_chapters()
                if chapters:
                    all_text = "\n\n".join(
                        _ctrl.load_chapter(c) for c in chapters
                    )
                    out_path = out_dir / "export_final.txt"
                    out_path.write_text(all_text, encoding="utf-8")
                    _ctrl.emit_log("System", "", "SUCCESS",
                                    f"📦 已导出 {len(chapters)} 章到: {out_path}")
                else:
                    _ctrl.emit_log("System", "", "WARNING", "没有章节可导出")

        elif export_type == "synopsis":
            synopsis = out_dir / "synopsis.txt"
            if synopsis.exists():
                content = synopsis.read_text(encoding="utf-8")
                _ctrl.emit_log("System", "", "SUCCESS",
                                f"📦 梗概: {content[:100]}...")
            else:
                _ctrl.emit_log("System", "", "WARNING", "未生成梗概，请完成创作流程")

        elif export_type == "cover":
            cover_dir = out_dir / "covers"
            brief = cover_dir / "cover_brief.json"
            prompt = cover_dir / "cover_prompt.txt"
            if brief.exists() or prompt.exists():
                _ctrl.emit_log("System", "", "SUCCESS",
                                f"📦 封面简报已存在: {cover_dir}")
            else:
                _ctrl.emit_log("System", "", "WARNING", "未生成封面简报，请完成创作流程")

    except Exception as e:
        _ctrl.emit_log("System", "", "ERROR", f"导出失败: {e}")


# ======================================================================
# 回调: 视图
# ======================================================================

def _on_toggle_log() -> None:
    """切换日志面板可见性。"""
    tag = log_panel.WINDOW_TAG
    if dpg.does_item_exist(tag):
        current = dpg.is_item_shown(tag)
        if current:
            dpg.hide_item(tag)
            dpg.configure_item("editor_area", height=-1)
        else:
            dpg.show_item(tag)
            dpg.configure_item("editor_area", height=-220)


def _on_viewport_resize() -> None:
    """视口大小变化时，同步调整主窗口尺寸。"""
    if dpg.does_item_exist("primary_window"):
        vp_width = dpg.get_viewport_client_width()
        vp_height = dpg.get_viewport_client_height()
        dpg.configure_item("primary_window", width=vp_width, height=vp_height)


# ======================================================================
# 回调: 后台任务状态变更
# ======================================================================

def _on_phase_change_from_job(phase_key: str) -> None:
    """后台任务切换到新阶段时的回调（由 poll_events 在主线程调用）。"""
    sidebar.update_phase_status(phase_key)


def _on_job_done(success: bool) -> None:
    """后台任务完成时的回调（由 poll_events 在主线程调用）。"""
    if success:
        _ctrl.emit_log("System", "", "SUCCESS", "🎉 创作任务顺利完成")
    else:
        _ctrl.emit_log("System", "", "WARNING", "⚠️ 创作任务被中断")
    # 刷新编辑器以展示新生成的内容
    _refresh_all_editors()


# ======================================================================
# 日志轮询（主线程每帧调用）
# ======================================================================

def _poll_logs() -> None:
    """从 log_queue 取出所有等待中的日志并更新 GUI。

    此函数在主线程的 render loop 中每帧调用。通过 LOG_POLL_INTERVAL
    限流，避免高帧率下空轮询浪费 CPU。
    """
    global _last_poll_time
    now = time.monotonic()
    if now - _last_poll_time < LOG_POLL_INTERVAL:
        return
    _last_poll_time = now
    _ctrl.poll_events()


def _handle_log_entry(entry: GUILogEntry) -> None:
    """处理一条普通日志：追加到日志面板 + 更新相关状态。

    此函数由 controller.poll_events() 在主线程调用（作为 _on_log 回调），
    因此可以安全操作 GUI。特殊事件（阶段变更/任务完成）已由 poll_events
    分发到对应回调，不会到达此处。
    """
    # 追加到日志面板
    log_panel.append_log(entry)

    # 如果日志包含阶段信息，更新侧边栏的阶段指示器
    if entry.phase and entry.level == "SUCCESS":
        sidebar.update_phase_status(entry.phase)

    # 如果是错误，标记对应阶段
    if entry.level == "ERROR" and entry.phase:
        sidebar.set_phase_error(entry.phase)


# ======================================================================
# 模块入口
# ======================================================================

if __name__ == "__main__":
    main()
