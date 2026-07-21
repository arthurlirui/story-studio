"""Job 模型 — 管理多个并发的小说生成任务。

每个 Job 在 {base_dir}/jobs/{job_id}/ 下有独立的 knowledge/ + output/，
互不干扰。JobRunner 用 asyncio.Semaphore 限并发，index 持久化到
{base_dir}/jobs/index.json。

用法：
    runner = JobRunner(base_dir="./jobs", cfg=load_config())
    job_id = await runner.submit("一个关于剑客的故事", project_name="剑客")
    job = runner.get(job_id)
    await runner.cancel(job_id)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Job 状态常量
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"


@dataclass
class Job:
    """单次小说生成任务。"""
    id: str
    brief: str
    status: str = JOB_QUEUED
    phase: str = "idle"
    progress: tuple[int, int] = (0, 0)  # (current_chapter, total_chapters)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    knowledge_dir: str = ""
    output_dir: str = ""
    project_name: str = ""
    write_mode: str = "sequential"  # "sequential" | "batch"
    result: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # tuple → list 便于 JSON 序列化
        d["progress"] = list(self.progress)
        return d

    def touch(self) -> None:
        self.updated_at = time.time()


class JobRunner:
    """管理多并发小说任务的运行器。"""

    def __init__(
        self,
        base_dir: str | Path,
        cfg: Any,
        max_concurrent: int = 2,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._index_path = self.base_dir / "index.json"
        self._load_index()

    # ── Index persistence ──────────────────────────────────────

    def _load_index(self) -> None:
        """从 index.json 恢复已知 job 元数据（不恢复运行中状态）。"""
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            for item in data.get("jobs", []):
                jid = item.get("id", "")
                if not jid:
                    continue
                # 重启后，原本 running 的 job 标记为 failed（无法恢复协程）
                status = item.get("status", JOB_QUEUED)
                if status == JOB_RUNNING:
                    status = JOB_FAILED
                    item["error"] = item.get("error") or "进程重启，运行中任务中断"
                job = Job(
                    id=jid,
                    brief=item.get("brief", ""),
                    status=status,
                    phase=item.get("phase", "idle"),
                    progress=tuple(item.get("progress", [0, 0])),
                    created_at=float(item.get("created_at", time.time())),
                    updated_at=float(item.get("updated_at", time.time())),
                    knowledge_dir=item.get("knowledge_dir", ""),
                    output_dir=item.get("output_dir", ""),
                    project_name=item.get("project_name", ""),
                    write_mode=item.get("write_mode", "sequential"),
                    result=item.get("result"),
                    error=item.get("error"),
                )
                self._jobs[jid] = job
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("加载 job index 失败: %s", e)

    def _save_index(self) -> None:
        """持久化 job index。"""
        data = {
            "jobs": [j.to_dict() for j in self._jobs.values()],
            "updated_at": time.time(),
        }
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._index_path)

    # ── Public API ─────────────────────────────────────────────

    async def submit(self, brief: str, project_name: str = "",
                     total_chapters: int | None = None,
                     write_mode: str = "sequential") -> str:
        """提交一个新 job，立即返回 job_id。任务在后台异步执行。

        Args:
            write_mode: "sequential" 逐章串行；"batch" 批次并行（每批 batch_size 章）。
        """
        jid = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        job_dir = self.base_dir / jid
        knowledge_dir = str(job_dir / "knowledge")
        output_dir = str(job_dir / "output")

        job = Job(
            id=jid,
            brief=brief,
            project_name=project_name,
            knowledge_dir=knowledge_dir,
            output_dir=output_dir,
            write_mode=write_mode if write_mode in ("sequential", "batch") else "sequential",
        )
        self._jobs[jid] = job
        self._save_index()

        # 启动后台任务
        task = asyncio.create_task(self._run_job(job, total_chapters))
        self._tasks[jid] = task
        return jid

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    async def cancel(self, job_id: str) -> bool:
        """取消一个 job。返回是否成功取消。"""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status in (JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELLED):
            return False
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
        job.status = JOB_CANCELLED
        job.touch()
        self._save_index()
        return True

    # ── Internal runner ────────────────────────────────────────

    async def _run_job(self, job: Job, total_chapters: int | None) -> None:
        """单个 job 的完整生命周期：planning → building → outlining → writing → complete。"""
        # 延迟导入避免循环依赖
        from orchestrator import StoryOrchestrator
        from agents.llm_client import LLMClient, init_client

        async with self._semaphore:
            job.status = JOB_RUNNING
            job.touch()
            self._save_index()

            try:
                # 构造该 job 专属的 cfg（覆盖路径）
                import copy
                cfg = copy.deepcopy(self.cfg)
                cfg.knowledge_dir = job.knowledge_dir
                cfg.output_dir = job.output_dir

                # 每个 job 独立的 LLM client（独立连接池）
                client = LLMClient(
                    base_url=cfg.llm_base_url,
                    api_key=cfg.llm_api_key,
                    default_model=cfg.main_model,
                )

                orch = StoryOrchestrator(cfg, client=client)
                if job.project_name:
                    orch.project_name = job.project_name

                # 用 TaskPlanner 驱动整个 pipeline（数据驱动 7 任务清单，支持断点续跑）
                from planner import TaskPlanner
                planner = TaskPlanner(
                    orch, orch.knowledge, cfg, orch.worklog,
                    plan_path=Path(job.knowledge_dir) / "task_plan.json",
                )
                # 默认总章节数：未指定时给一个合理默认值
                total = total_chapters or 10
                planner.build_plan(
                    brief=job.brief,
                    total_chapters=total,
                    write_mode=job.write_mode,
                    job_id=job.id,
                )

                def _on_progress(task) -> None:
                    job.phase = task.phase
                    # 进度按已完成任务数 / 总任务数近似
                    done_count = sum(
                        1 for t in planner.plan.tasks
                        if t.status in ("done", "skipped")
                    )
                    total_count = len(planner.plan.tasks)
                    if task.phase == "writing":
                        # writing 阶段保留章节粒度进度
                        job.progress = (orch.current_chapter, orch.total_chapters or total)
                    else:
                        job.progress = (done_count, total_count)
                    job.touch()
                    self._save_index()

                await planner.run_all(on_progress=_on_progress, stop_on_failure=True)

                # 完稿阶段产物预览
                last_task = next(
                    (t for t in planner.plan.tasks if t.phase == "complete"),
                    None,
                )
                preview = (last_task.result_excerpt if last_task else "")[:500]

                job.status = JOB_SUCCEEDED
                job.result = {
                    "project_name": orch.project_name,
                    "total_chapters": orch.total_chapters or total,
                    "cost": orch._cost_summary(),
                    "preview": preview,
                }
                job.phase = "complete"
                job.touch()
                self._save_index()

            except asyncio.CancelledError:
                job.status = JOB_CANCELLED
                job.touch()
                self._save_index()
                raise
            except Exception as e:
                logger.exception("Job %s 失败", job.id)
                job.status = JOB_FAILED
                job.error = str(e)
                job.touch()
                self._save_index()
