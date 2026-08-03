"""``ss jobs`` - 管理后台 Job。"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer

from cli._common import console, print_jobs_table, print_json, status_icon, status_style

app = typer.Typer(
    name="jobs",
    help="管理后台 Job",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _get_runner():
    from config import load_config
    from jobs import JobRunner
    cfg = load_config()
    return JobRunner(base_dir="jobs", cfg=cfg)


@app.command("list")
def jobs_list(
    status: Optional[str] = typer.Option(
        None, "--status", "-s",
        help="按状态过滤：queued/running/succeeded/failed/cancelled/recoverable",
    ),
    fmt: str = typer.Option("table", "--format", "-f", help="输出格式：table | json"),
) -> None:
    """列出所有后台 Job。"""
    runner = _get_runner()
    jobs = runner.list()
    if status:
        jobs = [j for j in jobs if j.status == status]

    if not jobs:
        console.print("[dim]📭 暂无后台 Job。用 [bold]ss submit \"<需求>\"[/bold] 创建。[/dim]")
        return

    if fmt == "json":
        print_json([j.to_dict() for j in jobs])
    else:
        print_jobs_table(jobs)


@app.command("show")
def jobs_show(
    job_id: str = typer.Argument(..., help="Job ID"),
    fmt: str = typer.Option("table", "--format", "-f", help="输出格式：table | json"),
) -> None:
    """查看单个 Job 详情。"""
    runner = _get_runner()
    job = runner.get(job_id)
    if job is None:
        console.print(f"[red]❌ Job {job_id} 不存在[/red]")
        raise typer.Exit(1)

    if fmt == "json":
        print_json(job.to_dict())
    else:
        d = job.to_dict()
        console.print(f"\n[bold cyan]Job {d['id']}[/bold cyan]")
        console.print(f"  状态: [{status_style(d['status'])}]{status_icon(d['status'])} {d['status']}[/{status_style(d['status'])}]")
        console.print(f"  阶段: {d['phase']}")
        console.print(f"  项目: {d.get('project_name') or '(未命名)'}")
        console.print(f"  进度: {d['progress']}")
        if d.get("task_progress"):
            console.print(f"  任务进度: {d['task_progress']}")
        console.print(f"  写作模式: {d.get('write_mode', '-')}")
        console.print(f"  knowledge: {d.get('knowledge_dir', '-')}")
        console.print(f"  output:    {d.get('output_dir', '-')}")
        if d.get("error"):
            console.print(f"  [red]错误: {d['error']}[/red]")
        if d.get("result"):
            console.print(f"  [green]结果: {json.dumps(d['result'], ensure_ascii=False)[:200]}[/green]")
        console.print()


@app.command("cancel")
def jobs_cancel(
    job_id: str = typer.Argument(..., help="Job ID"),
    all_running: bool = typer.Option(False, "--all", help="取消所有运行中/排队中的 Job"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
) -> None:
    """取消 Job（运行中/排队中）。"""
    from cli.main import cli_state

    async def _go():
        runner = _get_runner()
        if all_running:
            targets = [j for j in runner.list() if j.status in ("running", "queued")]
            if not targets:
                console.print("[dim]无运行中/排队中的 Job[/dim]")
                return
            if not yes and not cli_state["no_interaction"]:
                for j in targets:
                    console.print(f"  将取消: {j.id} [{j.status}] {j.project_name}")
                if not typer.confirm("确认取消以上所有 Job?"):
                    raise typer.Abort()
            for j in targets:
                ok = await runner.cancel(j.id)
                console.print(f"  {'✅' if ok else '⚠️'} {j.id}")
        else:
            ok = await runner.cancel(job_id)
            if ok:
                console.print(f"[green]✅ 已取消 {job_id}[/green]")
            else:
                console.print(f"[red]❌ 取消失败（job 不存在或已结束）[/red]")

    asyncio.run(_go())


@app.command("retry")
def jobs_retry(
    job_id: str = typer.Argument(..., help="Job ID（须为 failed/recoverable 状态）"),
) -> None:
    """重跑失败的 Job（从 task_plan.json 断点续跑）。"""
    from jobs import JOB_FAILED, JOB_RECOVERABLE, JOB_RUNNING, JOB_QUEUED

    async def _go():
        runner = _get_runner()
        job = runner.get(job_id)
        if job is None:
            console.print(f"[red]❌ Job {job_id} 不存在[/red]")
            raise typer.Exit(1)
        if job.status not in (JOB_FAILED, JOB_RECOVERABLE):
            console.print(f"[red]❌ Job 状态为 {job.status}，仅 failed/recoverable 可重跑[/red]")
            raise typer.Exit(1)
        # 触发 resume：复用 runner 的 _run_job + load_plan 断点续跑
        import copy
        cfg = copy.deepcopy(runner.cfg)
        cfg.knowledge_dir = job.knowledge_dir
        cfg.output_dir = job.output_dir
        job.status = JOB_QUEUED
        job.error = None
        runner._save_index()
        task = asyncio.create_task(runner._run_job(job, None))
        runner._tasks[job.id] = task
        console.print(f"[green]✅ 已重新排队 {job_id}，后台执行中[/green]")
        try:
            await task
        except Exception as e:
            console.print(f"[red]❌ 重跑失败: {e}[/red]")

    asyncio.run(_go())
