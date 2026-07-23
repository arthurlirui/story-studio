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
import threading
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
    # H2 修复：progress 语义在写作阶段是 (current_chapter, total_chapters)，
    # 在其他阶段是 (已完成任务数, 总任务数)。task_progress 显式记录任务粒度进度，
    # 仅在非写作阶段填充；写作阶段为 None（写作时直接看 progress）。
    progress: tuple[int, int] = (0, 0)
    task_progress: tuple[int, int] | None = None
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
        d["task_progress"] = list(self.task_progress) if self.task_progress is not None else None
        return d

    def touch(self) -> None:
        self.updated_at = time.time()


def make_on_progress(job: "Job", planner, orch, on_save=None):
    """H2/H4 共享：构造 run_all 的 on_progress 回调。

    - writing 阶段 progress 用 (current_chapter, total_chapters)
    - 其他阶段 progress 用 (done_tasks, total_tasks)，task_progress 同步填充
    - 每次回调调 on_save()（如 JobRunner._save_index）持久化
    """
    def _on_progress(task) -> None:
        job.phase = task.phase
        done_count = sum(
            1 for t in planner.plan.tasks
            if t.status in ("done", "skipped")
        )
        total_count = len(planner.plan.tasks)
        if task.phase == "writing":
            job.progress = (orch.current_chapter, orch.total_chapters or 0)
            job.task_progress = (done_count, total_count)
        else:
            job.progress = (done_count, total_count)
            job.task_progress = (done_count, total_count)
        job.touch()
        if on_save is not None:
            on_save()
    return _on_progress


def finalize_job_after_run_all(job: "Job", planner, orch, fallback_total: int) -> None:
    """H6 共享：run_all 完成后判定成功/失败，填充 result。

    若 summary 显示有失败任务则 raise RuntimeError，由调用方 except 走 JOB_FAILED。
    成功则填充 job.result / job.phase = "complete"。
    """
    summary = planner.summary()
    if summary.get("failed", 0) > 0:
        failed_tasks = [
            f"#{t.id}({t.phase})" for t in planner.plan.tasks
            if t.status == "failed"
        ]
        raise RuntimeError(
            f"任务失败 {summary['failed']} 个：{', '.join(failed_tasks)}"
        )
    last_task = next(
        (t for t in planner.plan.tasks if t.phase == "complete"),
        None,
    )
    preview = (last_task.result_excerpt if last_task else "")[:500]
    job.status = JOB_SUCCEEDED
    job.result = {
        "project_name": orch.project_name,
        "total_chapters": orch.total_chapters or fallback_total,
        "cost": orch._cost_summary(),
        "preview": preview,
    }
    job.phase = "complete"
    job.touch()


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
        # _save_index 是同步函数，会被多个并发 job 的 on_progress 回调 +
        # submit/cancel 从同一事件循环调用。threading.Lock 串行化写，避免
        # 并发 os.replace 同名 tmp 导致 index.json 撕裂（P0 修复）。
        self._index_lock = threading.Lock()
        # per-job 执行锁：确保同一 job 的 _run_job / API run_task / run_all
        # 不会并发编排同一 knowledge_dir，避免 task_plan.json / run_state.json
        # 互相覆盖（P0 修复）。
        self._job_locks: dict[str, asyncio.Lock] = {}
        self._load_index()

    # ── Index persistence ──────────────────────────────────────

    def _load_index(self) -> None:
        """从 index.json 恢复已知 job 元数据（不恢复运行中状态）。

        重启后处理孤儿目录的策略：
        - 原本 running 的 job 标记为 failed（无法恢复协程），其 knowledge_dir /
          output_dir 保留在盘上不自动删除，便于事后检查或断点续跑（TaskPlanner
          的 task_plan.json + run_state.json 仍在，可重新触发 /run-all 继续）。
        - 长期运行会积累此类孤儿目录，运维方应定期清理 jobs/ 下 status=failed
          且不再需要续跑的 job 目录，或迁移到归档存储。
        """
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
                elif status == JOB_QUEUED:
                    # P1 修复：queued 状态的 job（提交后未获信号量或进程刚 submit 就被杀）
                    # 无法恢复协程，标记为 failed。原代码保留 queued 导致永久卡死。
                    status = JOB_FAILED
                    item["error"] = item.get("error") or "进程重启，排队中任务未执行"
                tp = item.get("task_progress")
                job = Job(
                    id=jid,
                    brief=item.get("brief", ""),
                    status=status,
                    phase=item.get("phase", "idle"),
                    progress=tuple(item.get("progress", [0, 0])),
                    task_progress=tuple(tp) if tp else None,  # H2: 兼容旧 index
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
        """持久化 job index。

        用 threading.Lock 串行化并发写，tmp 文件名带唯一后缀避免多协程
        同时写同一 tmp 互相覆盖（P0 修复）。
        """
        data = {
            "jobs": [j.to_dict() for j in self._jobs.values()],
            "updated_at": time.time(),
        }
        # 唯一 tmp 名：pid + 对象 id + 时间戳纳秒，杜绝并发碰撞
        tmp = self._index_path.with_suffix(
            f".tmp.{os.getpid()}.{id(self)}.{time.time_ns()}"
        )
        with self._index_lock:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self._index_path)

    def _get_job_lock(self, job_id: str) -> asyncio.Lock:
        """获取（或创建）per-job 执行锁。"""
        lock = self._job_locks.get(job_id)
        if lock is None:
            lock = asyncio.Lock()
            self._job_locks[job_id] = lock
        return lock

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
        """单个 job 的完整生命周期：research → innovate → planning → building → outlining → writing → complete。"""
        # 延迟导入避免循环依赖
        from orchestrator import StoryOrchestrator
        from agents.llm_client import LLMClient

        async with self._semaphore:
            # per-job 锁：防止 API 端点（run_task/run_all）与 _run_job 并发
            # 编排同一 knowledge_dir（P0 修复）。
            async with self._get_job_lock(job.id):
                job.status = JOB_RUNNING
                job.touch()
                self._save_index()

                # 构造该 job 专属的 cfg（覆盖路径）
                import copy
                cfg = copy.deepcopy(self.cfg)
                cfg.knowledge_dir = job.knowledge_dir
                cfg.output_dir = job.output_dir

                # 每个 job 独立的 LLM client（独立连接池）。
                # 在 finally 中关闭，确保成功/失败/取消任何路径都不泄漏连接池。
                client = LLMClient(
                    base_url=cfg.llm_base_url,
                    api_key=cfg.llm_api_key,
                    default_model=cfg.main_model,
                )
                try:
                    orch = StoryOrchestrator(cfg, client=client)
                    if job.project_name:
                        orch.project_name = job.project_name

                    # 用 TaskPlanner 驱动整个 pipeline（数据驱动 7 任务清单，支持断点续跑）
                    from planner import TaskPlanner
                    planner = TaskPlanner(
                        orch, orch.knowledge, cfg, orch.worklog,
                        plan_path=Path(job.knowledge_dir) / "task_plan.json",
                    )
                    # H1 修复：total_chapters 透传（None 时让 orchestrator 从 outline 解析），
                    # 不再硬编码 `or 10`。TaskPlanner.build_plan 接受 int | None。
                    planner.build_plan(
                        brief=job.brief,
                        total_chapters=total_chapters,  # 可能是 None
                        write_mode=job.write_mode,
                        job_id=job.id,
                    )

                    _on_progress = make_on_progress(
                        job, planner, orch, on_save=self._save_index
                    )

                    await planner.run_all(on_progress=_on_progress, stop_on_failure=True)

                    # H6 修复：run_all 在 stop_on_failure=True 时会吞掉异常，
                    # 这里通过 summary 判定失败 → raise → 走 except 走 JOB_FAILED
                    finalize_job_after_run_all(job, planner, orch, fallback_total=0)
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
                finally:
                    # 无论成功/失败/取消都关闭连接池。
                    # 注意：phase_complete 成功路径内部已 aclose，这里二次调用是幂等的（有 is_closed 守卫）。
                    try:
                        await client.aclose()
                    except Exception as e:
                        logger.warning("Job %s 关闭 LLM 连接池失败: %s", job.id, e)
