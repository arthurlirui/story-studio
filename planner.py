"""
📋 TaskPlanner — 计划任务模块

把小说创作 pipeline 拆成阶段级任务清单（research → innovate → planning →
building → outlining → writing → complete），按序执行，支持断点续跑和
单任务重跑。

持久化：{knowledge_dir}/task_plan.json（atomic write）。

用法：
    from planner import TaskPlanner
    planner = TaskPlanner(orch, orch.knowledge, cfg, orch.worklog)
    plan = planner.build_plan(brief, total_chapters=10)
    plan.save(plan_path)
    await planner.run_all(on_progress=lambda task: print(task.name, task.status))
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from config import StudioConfig
from orchestrator_state import (
    PHASE_RESEARCH, PHASE_INNOVATE,
    PHASE_PLANNING, PHASE_BUILDING, PHASE_OUTLINING,
    PHASE_WRITING, PHASE_COMPLETE,
)

logger = logging.getLogger(__name__)

# 任务状态
TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_DONE = "done"
TASK_FAILED = "failed"
TASK_SKIPPED = "skipped"


@dataclass
class Task:
    """单个阶段级任务。"""
    id: int
    name: str           # 中文显示名
    phase: str          # orchestrator phase 常量
    status: str = TASK_PENDING
    started_at: str | None = None
    completed_at: str | None = None
    result_excerpt: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskPlan:
    """完整任务清单。"""
    job_id: str
    brief: str
    total_chapters: int
    write_mode: str = "sequential"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    tasks: list[Task] = field(default_factory=list)

    def save(self, path: Path) -> None:
        """原子写到 task_plan.json。"""
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        # M3-dup 修复：复用 knowledge._atomic_write_text，避免逻辑重复
        from agents.knowledge import _atomic_write_text
        _atomic_write_text(
            path,
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
        )

    @classmethod
    def load(cls, path: Path) -> "TaskPlan | None":
        """从 task_plan.json 读取。文件不存在或损坏返回 None。"""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            tasks = [
                Task(
                    id=t.get("id", 0),
                    name=t.get("name", ""),
                    phase=t.get("phase", ""),
                    status=t.get("status", TASK_PENDING),
                    started_at=t.get("started_at"),
                    completed_at=t.get("completed_at"),
                    result_excerpt=t.get("result_excerpt", ""),
                    error=t.get("error"),
                )
                for t in data.get("tasks", [])
            ]
            return cls(
                job_id=data.get("job_id", ""),
                brief=data.get("brief", ""),
                total_chapters=int(data.get("total_chapters", 0)),
                write_mode=data.get("write_mode", "sequential"),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                tasks=tasks,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("加载 task_plan.json 失败: %s", e)
            return None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "brief": self.brief,
            "total_chapters": self.total_chapters,
            "write_mode": self.write_mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tasks": [t.to_dict() for t in self.tasks],
        }


# 标准任务清单定义：(name, phase)
_DEFAULT_TASK_DEFS = [
    ("调研", PHASE_RESEARCH),
    ("创新亮点", PHASE_INNOVATE),
    ("策划", PHASE_PLANNING),
    ("建立", PHASE_BUILDING),
    ("大纲", PHASE_OUTLINING),
    ("写作", PHASE_WRITING),
    ("完稿", PHASE_COMPLETE),
]


class TaskPlanner:
    """阶段级任务计划器。"""

    def __init__(
        self,
        orchestrator: Any,
        knowledge: Any,
        cfg: StudioConfig,
        worklog: Any,
        plan_path: Path | str | None = None,
    ):
        self.orch = orchestrator
        self.knowledge = knowledge
        self.cfg = cfg
        self.worklog = worklog
        self.plan_path = Path(plan_path) if plan_path else (
            Path(cfg.knowledge_dir) / "task_plan.json"
        )
        self.plan: TaskPlan | None = None

    # ── 构建清单 ────────────────────────────────────────────────

    def build_plan(
        self,
        brief: str,
        total_chapters: int | None = None,
        write_mode: str = "sequential",
        job_id: str = "",
    ) -> TaskPlan:
        """生成 7 任务清单。research_enabled=False 时把 research/innovate 标记 skipped。

        total_chapters=None 时 plan.total_chapters 存为 0，由 outlining 阶段的
        LLM outline 解析决定实际章节数（H1 修复：保留 orchestrator 原本的
        「从 outline 解析章节建议数」行为，不被硬编码默认值覆盖）。
        """
        tasks: list[Task] = []
        for i, (name, phase) in enumerate(_DEFAULT_TASK_DEFS, start=1):
            task = Task(id=i, name=name, phase=phase)
            if not self.cfg.research_enabled and phase in (PHASE_RESEARCH, PHASE_INNOVATE):
                task.status = TASK_SKIPPED
            tasks.append(task)

        self.plan = TaskPlan(
            job_id=job_id or getattr(self.orch, "job_id", ""),
            brief=brief,
            total_chapters=total_chapters or 0,
            write_mode=write_mode if write_mode in ("sequential", "batch") else "sequential",
            tasks=tasks,
        )
        self.plan.save(self.plan_path)
        return self.plan

    def load_plan(self) -> TaskPlan | None:
        """从盘上加载已有清单（断点续跑）。加载后把 running 任务重置为 pending。

        崩溃时 task 停在 running，next_task 只选 pending → 永久卡死。
        加载时重置 running → pending，让 run_all 能重新执行。
        """
        self.plan = TaskPlan.load(self.plan_path)
        if self.plan:
            for t in self.plan.tasks:
                if t.status == TASK_RUNNING:
                    t.status = TASK_PENDING
                    t.started_at = None
                    logger.info("恢复：任务 #%d %s 从 running 重置为 pending", t.id, t.name)
            self.plan.save(self.plan_path)
        return self.plan

    # ── 查询 ────────────────────────────────────────────────────

    def next_task(self) -> Task | None:
        """返回第一个 pending 任务（不重试 failed）。全部完成/已触达返回 None。"""
        if not self.plan:
            return None
        for t in self.plan.tasks:
            if t.status == TASK_PENDING:
                return t
        return None

    def summary(self) -> dict:
        """各状态计数。"""
        if not self.plan:
            return {"total": 0, "pending": 0, "running": 0,
                    "done": 0, "failed": 0, "skipped": 0}
        counts = {"total": len(self.plan.tasks), "pending": 0, "running": 0,
                  "done": 0, "failed": 0, "skipped": 0}
        for t in self.plan.tasks:
            counts[t.status] = counts.get(t.status, 0) + 1
        return counts

    # ── 状态变更 ────────────────────────────────────────────────

    def _mark(self, task_id: int, status: str,
              result_excerpt: str = "", error: str | None = None) -> None:
        if not self.plan:
            return
        for t in self.plan.tasks:
            if t.id == task_id:
                t.status = status
                if status == TASK_RUNNING:
                    t.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                elif status in (TASK_DONE, TASK_FAILED, TASK_SKIPPED):
                    t.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                if result_excerpt:
                    t.result_excerpt = result_excerpt[:300]
                if error:
                    t.error = error[:500]
                break
        self.plan.save(self.plan_path)

    def mark_done(self, task_id: int, result_excerpt: str = "") -> None:
        self._mark(task_id, TASK_DONE, result_excerpt)

    def mark_failed(self, task_id: int, error: str) -> None:
        self._mark(task_id, TASK_FAILED, error=error)

    def reset_task(self, task_id: int) -> None:
        """允许重跑：状态改回 pending，清空时间戳。"""
        if not self.plan:
            return
        for t in self.plan.tasks:
            if t.id == task_id:
                t.status = TASK_PENDING
                t.started_at = None
                t.completed_at = None
                t.result_excerpt = ""
                t.error = None
                break
        self.plan.save(self.plan_path)

    # ── 执行 ────────────────────────────────────────────────────

    async def run_task(self, task: Task) -> str:
        """按 task.phase 分派到对应 orchestrator.phase_* 方法。返回产物摘要。"""
        if not self.plan:
            raise RuntimeError("TaskPlanner: plan 未初始化，先调用 build_plan 或 load_plan")

        logger.info("TaskPlanner: 运行任务 #%d %s (phase=%s)", task.id, task.name, task.phase)
        self._mark(task.id, TASK_RUNNING)

        try:
            result = await self._dispatch(task)
            self.mark_done(task.id, result_excerpt=result)
            await self.worklog.append(
                phase=task.phase, agent="TaskPlanner", role="planner",
                action="task", excerpt=f"#{task.id} {task.name} done",
            )
            return result
        except Exception as e:
            logger.exception("TaskPlanner: 任务 #%d 失败: %s", task.id, e)
            self.mark_failed(task.id, str(e))
            await self.worklog.append(
                phase=task.phase, agent="TaskPlanner", role="planner",
                action="task", error=f"#{task.id} {task.name} failed: {e}",
            )
            raise

    async def _dispatch(self, task: Task) -> str:
        """分派到 orchestrator 对应 phase 方法。"""
        phase = task.phase
        # m5 修复：_dispatch 仅在 run_all/run_task 中被调用，self.plan 必非 None
        brief = self.plan.brief

        if phase == PHASE_RESEARCH:
            return await self.orch.phase_research(brief)
        if phase == PHASE_INNOVATE:
            # M5 修复：传完整的 novel brief 而非 project_name（短书名不足以表达题材）
            return await self.orch.phase_innovate(brief)
        if phase == PHASE_PLANNING:
            return await self.orch.phase_planning(brief)
        if phase == PHASE_BUILDING:
            return await self.orch.phase_building()
        if phase == PHASE_OUTLINING:
            # H1 修复：plan.total_chapters=0（用户未指定）时传 None，
            # 让 orchestrator 从 outline 解析「建议章节数」
            return await self.orch.phase_outlining(
                total_chapters=self.plan.total_chapters or None,
            )
        if phase == PHASE_WRITING:
            return await self._run_writing_phase()
        if phase == PHASE_COMPLETE:
            return await self.orch.phase_complete()
        raise ValueError(f"TaskPlanner: 未知 phase={phase}")

    async def _run_writing_phase(self) -> str:
        """写作阶段：按 write_mode 决定串行 / 批次并行。

        H1 修复后的优先级：
        1. plan.total_chapters（用户显式指定）
        2. orchestrator.total_chapters（outlining 阶段从 outline 解析得到）
        3. 兜底 10（防止 0 章导致空跑）

        断电恢复：用 is_chapter_delivered 跳过已交付章节（有摘要 = 走完 PASS/耗尽流程）。
        """
        plan_total = self.plan.total_chapters
        total = plan_total or self.orch.total_chapters or 10
        write_mode = self.plan.write_mode

        if write_mode == "batch":
            batch_size = max(1, self.cfg.batch_size)
            ch = 1
            while ch <= total:
                # 跳过已交付的章节（断电恢复）
                if self.orch.knowledge.is_chapter_delivered(ch):
                    logger.info("恢复：第 %d 章已交付，跳过", ch)
                    ch += 1
                    continue
                count = min(batch_size, total - ch + 1)
                # 裁剪批次尾部已交付的章节
                while count > 1 and self.orch.knowledge.is_chapter_delivered(ch + count - 1):
                    count -= 1
                await self.orch.phase_writing_batch(ch, count)
                ch += count
        else:
            for ch in range(1, total + 1):
                if self.orch.knowledge.is_chapter_delivered(ch):
                    logger.info("恢复：第 %d 章已交付，跳过", ch)
                    continue
                await self.orch.phase_writing(ch)

        return f"写作完成：{total} 章"

    async def run_all(
        self,
        on_progress: Callable[[Task], None] | None = None,
        stop_on_failure: bool = True,
    ) -> str:
        """循环执行所有未完成任务。

        Args:
            on_progress: 每个任务完成后的回调（同步）
            stop_on_failure: 任务失败时是否中断后续（默认 True）
        """
        if not self.plan:
            raise RuntimeError("TaskPlanner: plan 未初始化")

        last_result = ""
        while True:
            task = self.next_task()
            if task is None:
                break
            try:
                last_result = await self.run_task(task)
                if on_progress:
                    on_progress(task)
            except Exception as e:
                if on_progress:
                    on_progress(task)
                if stop_on_failure:
                    logger.error("TaskPlanner: 任务 #%d 失败，停止后续: %s", task.id, e)
                    break
                # 继续下一个任务
        return last_result
