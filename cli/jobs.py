"""``ss jobs`` - 管理后台 Job。"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer

from cli._common import console, print_jobs_table, print_json, print_tasks_table, status_icon, status_style, get_runner

app = typer.Typer(
    name="jobs",
    help="管理后台 Job",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _get_runner():
    return get_runner()


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

    async def _go():
        runner = _get_runner()
        try:
            await runner.retry(job_id)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✅ 已重新排队 {job_id}，后台执行中[/green]")
        # 等待后台任务完成
        task = runner._tasks.get(job_id)
        if task is not None:
            try:
                await task
                console.print(f"[green]✅ Job {job_id} 重跑完成[/green]")
            except Exception as e:
                console.print(f"[red]❌ 重跑失败: {e}[/red]")

    asyncio.run(_go())


# ── tasks 子命令组 ───────────────────────────────────────────────

tasks_app = typer.Typer(
    name="tasks",
    help="任务计划管理（查看/运行单任务/run-all/resume）",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _load_task_plan(runner, job_id: str):
    """加载 job 的 TaskPlan，返回 (job, plan) 或 raise。"""
    from pathlib import Path
    from planner import TaskPlan

    job = runner.get(job_id)
    if job is None:
        console.print(f"[red]❌ Job {job_id} 不存在[/red]")
        raise typer.Exit(1)
    plan_path = Path(job.knowledge_dir) / "task_plan.json"
    plan = TaskPlan.load(plan_path)
    if plan is None:
        console.print(f"[dim]Job {job_id} 无 task_plan.json（尚未开始或未 build_plan）[/dim]")
        raise typer.Exit(1)
    return job, plan


@tasks_app.callback(invoke_without_command=True)
def tasks_show(
    job_id: str = typer.Argument(..., help="Job ID"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """查看 Job 的任务清单。"""

    runner = _get_runner()
    job, plan = _load_task_plan(runner, job_id)

    if fmt == "json":
        print_json(plan.to_dict())
        return

    console.print(f"\n[bold cyan]Job {job_id}[/bold cyan] — 任务清单（{len(plan.tasks)} 个）")
    console.print(f"  项目: {job.project_name or '(未命名)'}")
    console.print(f"  写作模式: {plan.write_mode}")
    console.print(f"  目标章节: {plan.total_chapters or '?'}")
    print_tasks_table(plan.tasks)
    console.print()


@tasks_app.command("run")
def tasks_run(
    job_id: str = typer.Argument(..., help="Job ID"),
    task_n: int = typer.Argument(..., min=1, help="任务号（1-based，从 tasks 查看）"),
) -> None:
    """运行第 N 个计划任务。"""

    async def _go():
        runner = _get_runner()
        try:
            result = await runner.run_task(job_id, task_n)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✅ 任务 #{task_n} 完成[/green]")
        if result:
            console.print(result[:800])

    asyncio.run(_go())


@tasks_app.command("run-all")
def tasks_run_all(
    job_id: str = typer.Argument(..., help="Job ID"),
) -> None:
    """运行所有待执行任务（顺序执行，遇错停止）。"""

    async def _go():
        runner = _get_runner()
        console.print(f"[cyan]🚀 运行 Job {job_id} 的所有待执行任务...[/cyan]")
        try:
            await runner.run_all_tasks(job_id)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✅ 所有任务执行完毕[/green]")

    asyncio.run(_go())


@tasks_app.command("resume")
def tasks_resume(
    job_id: str = typer.Argument(..., help="Job ID（从断点恢复执行）"),
) -> None:
    """从断点恢复执行（等价于 run-all，从 task_plan.json 的 pending 任务继续）。"""

    async def _go():
        runner = _get_runner()
        job = runner.get(job_id)
        if job is None:
            console.print(f"[red]❌ Job {job_id} 不存在[/red]")
            raise typer.Exit(1)
        console.print(f"[cyan]🔄 从断点恢复 Job {job_id}...[/cyan]")
        try:
            await runner.run_all_tasks(job_id)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✅ 恢复执行完毕[/green]")

    asyncio.run(_go())


# 将 tasks 子命令组注册到 jobs app
app.add_typer(tasks_app, name="tasks", help="任务计划管理")
