"""
GUIController — 异步桥接层，连接 DearPyGUI 主线程与 StoryOrchestrator 后台任务。

架构:
  主线程 (DearPyGUI render loop)      后台线程 (asyncio event loop)
       │                                    │
       │── start_job(brief, ...) ───►       │
       │                                    │── orchestrator.phase_research()
       │                                    │── (log_queue.put(msg))
       │                                    │── orchestrator.phase_innovate()
       │                                    │── ...
       │◄── poll_logs() ────────────────────│
       │                                    │
       │── dearpygui.set_value()            │
       │   (更新日志面板、状态等)             │
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Log message model
# ---------------------------------------------------------------------------

# 特殊 agent 标记，用于在 log_queue 中传递非日志事件（阶段变更、任务完成）。
# 主线程 poll 时识别这些标记并触发对应回调，避免后台线程直接操作 GUI。
_EVENT_PHASE_CHANGE = "__PHASE_CHANGE__"
_EVENT_JOB_DONE = "__JOB_DONE__"

@dataclass
class GUILogEntry:
    """一条发给 GUI 日志面板的消息，也可携带控制事件。"""
    timestamp: float = field(default_factory=time.time)
    agent: str = ""
    phase: str = ""
    level: str = "INFO"        # INFO | WARNING | ERROR | SUCCESS
    message: str = ""
    excerpt: str = ""          # 内容预览（可选）


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class GUIController:
    """GUI 与 StoryOrchestrator 之间的桥接控制器。

    所有 orchestrator 操作在后台线程的 asyncio 事件循环中执行，
    结果通过 log_queue 传回主线程。
    """

    def __init__(self):
        self.log_queue: queue.Queue[GUILogEntry] = queue.Queue()

        # 后台线程相关
        self._job_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()

        # 项目组件（由 init_project() 或外部注入）
        self.orchestrator: Any = None   # StoryOrchestrator 实例
        self.store: Any = None          # KnowledgeStore 实例
        self.config: Any = None         # StudioConfig 实例

        # 回调（由 app.py 注册；均在主线程 poll 时调用，而非后台线程直接调用）
        self._on_log: Callable[[GUILogEntry], None] | None = None
        self._on_phase_change: Callable[[str], None] | None = None
        self._on_job_done: Callable[[bool], None] | None = None

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def init_project(self, config_dir: str | None = None) -> bool:
        """加载配置、初始化 LLM 客户端、创建 orchestrator 和 knowledge store。

        Returns:
            True 表示初始化成功，False 表示失败（缺少 API key 等）。
        """
        try:
            from config import load_config

            kd = Path(config_dir) if config_dir else None
            self.config = load_config(str(kd) if kd else "")

            if not self.config.llm_api_key:
                logger.warning("未配置 LLM API key，GUI 将以只读模式运行")
                self.store = self._create_store()
                return True

            # 初始化 LLM 客户端
            from agents.llm_client import init_client
            try:
                llm = init_client(
                    base_url=self.config.llm_base_url,
                    api_key=self.config.llm_api_key,
                    default_model=self.config.main_model,
                )
            except Exception as e:
                logger.warning(f"LLM 客户端初始化失败（将以只读模式运行）: {e}")
                self.store = self._create_store()
                return True

            # 延迟导入 orchestrator，确保 llm_client 已初始化
            # （orchestrator 模块内部 import 了 agents.llm_client 的全局 client 变量）
            from orchestrator import StoryOrchestrator
            self.orchestrator = StoryOrchestrator(self.config, client=llm)
            self.store = self.orchestrator.knowledge
            return True
        except Exception as e:
            logger.error(f"初始化项目失败: {e}")
            self.emit_log("System", "", "ERROR", f"初始化失败: {e}")
            return False

    def _create_store(self) -> Any:
        """创建独立的 KnowledgeStore（无 orchestrator 时使用）。"""
        from agents.knowledge import KnowledgeStore

        kd = self.config.knowledge_dir if self.config else "knowledge"
        sd = self.config.series_knowledge_dir if self.config else ""
        sr = self.config.series_research_dir if self.config else ""
        return KnowledgeStore(str(kd), str(sd), str(sr))

    # ------------------------------------------------------------------
    # 日志发送
    # ------------------------------------------------------------------

    def emit_log(self, agent: str, phase: str, level: str, message: str, excerpt: str = "") -> None:
        """向 log_queue 发送一条日志（线程安全，可从任意线程调用）。"""
        self.log_queue.put(GUILogEntry(
            agent=agent,
            phase=phase,
            level=level,
            message=message,
            excerpt=excerpt,
        ))

    def _emit_log(self, agent: str, phase: str, level: str, message: str, excerpt: str = "") -> None:
        """已废弃，请使用 emit_log。保留向后兼容。"""
        self.emit_log(agent, phase, level, message, excerpt)

    # ------------------------------------------------------------------
    # Job 启动与停止
    # ------------------------------------------------------------------

    def start_full_pipeline(
        self,
        brief: str,
        genre: str = "",
        total_chapters: int = 10,
        write_mode: str = "sequential",
    ) -> None:
        """在后台线程启动完整的 7 阶段创作流程。

        Args:
            brief: 创作梗概
            genre: 类型关键词（目前由 orchestrator 从 brief 文本自动检测，
                   此参数保留供未来显式 genre 传递使用）
            total_chapters: 目标章节数
            write_mode: "sequential" 或 "batch"
        """
        if self._job_thread and self._job_thread.is_alive():
            self.emit_log("System", "", "WARNING", "已有任务在运行中，请先停止")
            return

        if not self.orchestrator:
            self.emit_log("System", "", "ERROR", "未初始化 orchestrator（缺少 API key 或配置）")
            return

        self._stop_event.clear()
        self._job_thread = threading.Thread(
            target=self._run_async_job,
            args=(brief, genre, total_chapters, write_mode),
            daemon=True,
        )
        self._job_thread.start()
        self.emit_log("System", "", "INFO", "🎬 创作流程已启动")

    def start_single_phase(self, phase_name: str, brief: str = "") -> None:
        """在后台线程运行单个阶段。

        Args:
            phase_name: 阶段 key（research/innovate/.../complete）
            brief: 创作梗概（research/innovate/planning 阶段需要）
        """
        if self._job_thread and self._job_thread.is_alive():
            self.emit_log("System", "", "WARNING", "已有任务在运行中，请先停止")
            return

        if not self.orchestrator:
            self.emit_log("System", "", "ERROR", "未初始化 orchestrator")
            return

        self._stop_event.clear()
        self._job_thread = threading.Thread(
            target=self._run_async_phase,
            args=(phase_name, brief),
            daemon=True,
        )
        self._job_thread.start()

    def stop_job(self) -> None:
        """发送停止信号给后台任务。"""
        self._stop_event.set()
        self.emit_log("System", "", "WARNING", "⏹ 正在停止当前任务...")

    def is_running(self) -> bool:
        """检查后台任务是否正在运行。"""
        return self._job_thread is not None and self._job_thread.is_alive()

    # ------------------------------------------------------------------
    # 后台线程入口
    # ------------------------------------------------------------------

    def _run_async_job(self, brief: str, genre: str, total_chapters: int, write_mode: str) -> None:
        """后台线程：运行完整创作流程。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._async_full_pipeline(brief, genre, total_chapters, write_mode))
        except Exception as e:
            self.emit_log("System", "", "ERROR", f"流程异常: {e}")
        finally:
            self._loop = None
            loop.close()
            # 通过队列通知主线程任务完成（不在后台线程直接调用回调）
            self.log_queue.put(GUILogEntry(
                agent=_EVENT_JOB_DONE,
                message="success" if not self._stop_event.is_set() else "stopped",
            ))

    def _run_async_phase(self, phase_name: str, brief: str = "") -> None:
        """后台线程：运行单个阶段。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._async_single_phase(phase_name, brief))
        except Exception as e:
            self.emit_log("System", "", "ERROR", f"阶段 [{phase_name}] 异常: {e}")
        finally:
            self._loop = None
            loop.close()
            self.log_queue.put(GUILogEntry(
                agent=_EVENT_JOB_DONE,
                message="success" if not self._stop_event.is_set() else "stopped",
            ))

    # ------------------------------------------------------------------
    # Async 流程实现
    # ------------------------------------------------------------------

    async def _async_full_pipeline(
        self, brief: str, genre: str, total_chapters: int, write_mode: str
    ) -> None:
        """完整 7 阶段串联执行。"""
        orch = self.orchestrator
        phases = [
            ("research", "调研", lambda: orch.phase_research(brief)),
            ("innovate", "创新", lambda: orch.phase_innovate(brief)),
            ("planning", "企划", lambda: orch.phase_planning(brief)),
            ("building", "构建", lambda: orch.phase_building()),
            ("outlining", "大纲", lambda: orch.phase_outlining(total_chapters)),
        ]

        for phase_key, phase_label, phase_fn in phases:
            if self._stop_event.is_set():
                self.emit_log("System", phase_key, "WARNING", f"用户停止，跳过阶段: {phase_label}")
                return
            await self._run_phase(phase_key, phase_label, phase_fn)

        # 写作阶段
        if write_mode == "batch":
            self.emit_log("System", "writing", "INFO", f"📝 批量并行写作 {total_chapters} 章")
            for start in range(1, total_chapters + 1, orch.config.batch_size):
                if self._stop_event.is_set():
                    self.emit_log("System", "writing", "WARNING", "用户停止写作")
                    return
                count = min(orch.config.batch_size, total_chapters - start + 1)
                await self._run_phase(
                    "writing",
                    f"写作 (第{start}-{start+count-1}章)",
                    lambda s=start, c=count: orch.phase_writing_batch(s, c),
                )
        else:
            for ch in range(1, total_chapters + 1):
                if self._stop_event.is_set():
                    self.emit_log("System", "writing", "WARNING", f"用户停止写作（已完成 {ch-1} 章）")
                    return
                await self._run_phase(
                    "writing",
                    f"写作 (第{ch}章)",
                    lambda c=ch: orch.phase_writing(c),
                )

        # 完成
        await self._run_phase("complete", "完成", lambda: orch.phase_complete())

        self.emit_log("System", "", "SUCCESS", "🎉 创作流程全部完成！")

    async def _async_single_phase(self, phase_name: str, brief: str = "") -> None:
        """运行单个阶段。

        Args:
            phase_name: 阶段 key
            brief: 创作梗概（research/innovate/planning 阶段需要）
        """
        orch = self.orchestrator
        phase_map = {
            "research": ("调研", lambda: orch.phase_research(brief)),
            "innovate": ("创新", lambda: orch.phase_innovate(brief)),
            "planning": ("企划", lambda: orch.phase_planning(brief)),
            "building": ("构建", lambda: orch.phase_building()),
            "outlining": ("大纲", lambda: orch.phase_outlining(orch.total_chapters or 10)),
            "writing": ("写作", lambda: orch.phase_writing(
                min(orch.current_chapter + 1, orch.total_chapters or orch.current_chapter + 1)
            )),
            "complete": ("完成", lambda: orch.phase_complete()),
        }
        if phase_name not in phase_map:
            self.emit_log("System", phase_name, "ERROR", f"未知阶段: {phase_name}")
            return

        label, fn = phase_map[phase_name]
        await self._run_phase(phase_name, label, fn)
        self.emit_log("System", phase_name, "SUCCESS", f"阶段 [{label}] 完成")

    async def _run_phase(self, phase_key: str, phase_label: str, phase_fn) -> None:
        """执行单个阶段，带日志和阶段变更事件。"""
        self.emit_log("System", phase_key, "INFO", f"▶ 开始阶段: {phase_label}")
        # 通过队列通知主线程阶段变更（线程安全）
        self.log_queue.put(GUILogEntry(agent=_EVENT_PHASE_CHANGE, phase=phase_key))

        start_time = time.time()
        try:
            result = await phase_fn()
            elapsed = time.time() - start_time
            self.emit_log(
                "System", phase_key, "SUCCESS",
                f"✅ [{phase_label}] 完成 (耗时 {elapsed:.1f}s)",
                excerpt=result[:200] if isinstance(result, str) else "",
            )
        except Exception as e:
            elapsed = time.time() - start_time
            self.emit_log(
                "System", phase_key, "ERROR",
                f"❌ [{phase_label}] 失败 (耗时 {elapsed:.1f}s): {e}",
            )

    # ------------------------------------------------------------------
    # 知识库操作（线程安全 —— 只在主线程调用）
    # ------------------------------------------------------------------

    def load_world_settings(self) -> str:
        """读取世界观设定。"""
        if self.store:
            try:
                return self.store.load_world("settings")
            except Exception:
                return ""
        return ""

    def save_world_settings(self, content: str) -> None:
        """保存世界观设定。"""
        if self.store:
            self.store.save_world("settings", content)
            self.emit_log("System", "", "INFO", "💾 世界观设定已保存")

    def load_character(self, name: str) -> str:
        """读取角色档案。"""
        if self.store:
            try:
                return self.store.load_character(name)
            except Exception:
                return ""
        return ""

    def save_character(self, name: str, content: str) -> None:
        """保存角色档案。"""
        if self.store:
            self.store.save_character(name, content)
            self.emit_log("System", "", "INFO", f"💾 角色 [{name}] 已保存")

    def list_characters(self) -> list[str]:
        """列出所有角色名。"""
        if self.store:
            return self.store.list_characters()
        return []

    def load_outline(self) -> str:
        """读取故事大纲。"""
        if self.store:
            try:
                return self.store.load_outline()
            except Exception:
                return ""
        return ""

    def save_outline(self, content: str) -> None:
        """保存故事大纲。"""
        if self.store:
            self.store.save_outline(content)
            self.emit_log("System", "", "INFO", "💾 故事大纲已保存")

    def load_chapter(self, chapter_num: int) -> str:
        """读取指定章节。"""
        if self.store:
            try:
                return self.store.load_chapter(chapter_num)
            except Exception:
                return ""
        return ""

    def save_chapter(self, chapter_num: int, content: str, author: str = "") -> None:
        """保存章节。"""
        if self.store:
            self.store.save_chapter(chapter_num, content, author or "用户编辑")
            self.emit_log("System", "", "INFO", f"💾 第 {chapter_num} 章已保存")

    def list_chapters(self) -> list[int]:
        """列出所有章节号。"""
        if self.store:
            return self.store.list_chapters()
        return []

    def load_research(self, topic: str) -> str:
        """读取调研资料。"""
        if self.store:
            try:
                return self.store.load_research(topic)
            except Exception:
                return ""
        return ""

    def list_research_topics(self) -> list[str]:
        """列出所有调研主题。"""
        if self.store:
            return self.store.list_research_topics()
        return []

    def get_orchestrator_status(self) -> dict:
        """获取 orchestrator 状态。"""
        if self.orchestrator:
            try:
                return self.orchestrator.get_status()
            except Exception as e:
                logger.warning(f"get_status() 失败: {e}")
        return {}

    def get_agent_names(self) -> list[str]:
        """获取 agent 名称列表。"""
        if self.orchestrator and hasattr(self.orchestrator, 'agents'):
            return list(self.orchestrator.agents.keys())
        return []

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def set_on_log(self, callback: Callable[[GUILogEntry], None]) -> None:
        self._on_log = callback

    def set_on_phase_change(self, callback: Callable[[str], None]) -> None:
        self._on_phase_change = callback

    def set_on_job_done(self, callback: Callable[[bool], None]) -> None:
        self._on_job_done = callback

    # ------------------------------------------------------------------
    # 主线程轮询 — 处理队列中的日志和事件
    # ------------------------------------------------------------------

    def poll_events(self) -> None:
        """从 log_queue 取出所有等待中的消息并分发。

        此方法**只能在主线程调用**（如 DearPyGUI 渲染循环中每帧调用）。
        普通日志交给 _on_log 回调；特殊事件（阶段变更、任务完成）
        交给对应回调。这样确保所有 GUI 操作都在主线程执行。
        """
        while True:
            try:
                entry = self.log_queue.get_nowait()
            except queue.Empty:
                break

            # 特殊事件处理
            if entry.agent == _EVENT_PHASE_CHANGE:
                if self._on_phase_change:
                    self._on_phase_change(entry.phase)
                continue
            if entry.agent == _EVENT_JOB_DONE:
                if self._on_job_done:
                    self._on_job_done(entry.message == "success")
                continue

            # 普通日志
            if self._on_log:
                self._on_log(entry)
