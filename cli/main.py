"""Story Studio CLI 根应用。

组合各子命令组（run / jobs / list / export / config / agents / status / repl），
提供全局选项（-v / --config / -n）。

设计要点：
- **懒加载**：子命令组用 ``app.add_typer(module.app, name=...)`` 在调用时才 import，
  避免 ``ss --help`` 时拉起 93KB 的 orchestrator.py 拖慢启动。
- **no_args_is_help**：裸 ``ss`` 直接打印帮助而非静默退出。
- **向后兼容**：``main.py`` 委托到 ``cli.main:app``，``python main.py --new "..."`` 仍可用。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

# 全局状态：根 callback 写入，子命令通过 cli.state 读取。
# 用 dict 而非 dataclass，避免子命令 import 时触发循环依赖。
cli_state: dict = {
    "verbose": 0,
    "config_path": None,
    "no_interaction": False,
}


app = typer.Typer(
    name="ss",
    help="🎭 Story Studio - 多 Agent 协作的 AI 小说创作平台 CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    # 避免把 API key 等局部变量泄露到异常 traceback
    pretty_exceptions_show_locals=False,
)


@app.callback()
def main_callback(
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True,
        help="详细输出：-v INFO, -vv DEBUG, -vvv 全量",
    ),
    config: Optional[Path] = typer.Option(
        None, "--config",
        help="指定 settings.yaml 路径（默认 config/settings.yaml）",
        envvar="STORY_STUDIO_CONFIG",
    ),
    no_interaction: bool = typer.Option(
        False, "--no-interaction", "-n",
        help="非交互模式：不弹出确认提示，全部用默认值（CI 友好）",
    ),
) -> None:
    """Story Studio 命令行工具。

    全局选项须放在子命令前，例如 ``ss -v jobs list``。
    """
    cli_state["verbose"] = verbose
    cli_state["config_path"] = str(config) if config else None
    cli_state["no_interaction"] = no_interaction

    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── 子命令注册（懒加载：import 在模块顶层执行，但模块本身只在此处被引用）──
# 每个 sub-app 文件只在首次被 add_typer 引用时才被 Python import，
# 而 add_typer 仅注册元数据；真正的命令函数体在用户调用该子命令时才执行。
# 由于这些文件内部对 orchestrator 等重模块的 import 都放在函数体内，
# ``ss --help`` 不会触发重模块加载。

from cli import run as _run  # noqa: E402
from cli import jobs as _jobs  # noqa: E402
from cli import novels as _novels  # noqa: E402
from cli import export as _export  # noqa: E402
from cli import config_cmd as _config  # noqa: E402
from cli import agents as _agents  # noqa: E402
from cli import status as _status  # noqa: E402
from cli import repl as _repl  # noqa: E402

app.add_typer(_run.app, name="run", help="🚀 运行生成管线（pipeline/short/stage/polish）")
app.add_typer(_jobs.app, name="jobs", help="📋 管理后台 Job（list/show/cancel/retry）")
app.add_typer(_novels.app, name="list", help="📚 列出小说/系列/章节")
app.add_typer(_export.app, name="export", help="📦 导出成品（final/covers）")
app.add_typer(_config.app, name="config", help="⚙️ 查看与编辑配置（get/set/show/path）")
app.add_typer(_agents.app, name="agents", help="🤖 智能体团队（list/inspect）")
app.add_typer(_status.app, name="status", help="📊 系统/项目状态", hidden=False)
app.add_typer(_repl.app, name="repl", help="💬 交互式 REPL（迁移自 main.py）")


@app.command()
def submit(
    brief: str = typer.Argument(..., help="创作需求/企划描述"),
    name: str = typer.Option("", "--name", "-n", help="项目名（书名）"),
    chapters: int = typer.Option(None, "--chapters", "-c", min=1, max=200, help="目标章节数"),
    mode: str = typer.Option("sequential", "--mode", "-m", help="写作模式：sequential | batch"),
    wait: bool = typer.Option(False, "--wait", help="阻塞等待 Job 完成后再退出（默认提交后立即返回）"),
) -> None:
    """提交一个后台小说生成 Job。

    默认 ``--no-wait``：提交后立即返回 job_id，Job 在后台异步执行。
    加 ``--wait`` 则阻塞至 Job 完成（CI/脚本友好）。
    """
    import asyncio
    from cli._common import console, get_runner

    runner = get_runner()

    async def _go():
        job_id = await runner.submit(
            brief=brief, project_name=name,
            total_chapters=chapters, write_mode=mode,
        )
        console.print(f"[green]✅ 已提交后台 Job:[/green] [cyan]{job_id}[/cyan]")
        console.print(f"  查看状态: [bold]ss jobs show {job_id}[/bold]")
        console.print(f"  取消:     [bold]ss jobs cancel {job_id}[/bold]")

        if not wait:
            console.print(f"[dim]Job 在后台执行中，用 ss jobs show {job_id} 查看进度[/dim]")
            return

        # --wait：等待后台任务完成
        task = runner._tasks.get(job_id)
        if task is not None:
            try:
                await task
                console.print(f"[green]✅ Job {job_id} 已完成[/green]")
            except asyncio.CancelledError:
                console.print(f"[yellow]⏹️ Job {job_id} 已取消[/yellow]")
            except Exception as e:
                console.print(f"[red]❌ Job {job_id} 失败: {e}[/red]")

    asyncio.run(_go())


@app.command()
def gui() -> None:
    """🖥️ 启动 DearPyGUI 桌面创作界面。"""
    from gui.app import main as gui_main
    gui_main()


def run() -> None:
    """entry point: ``ss`` 命令实际调用。"""
    app()


if __name__ == "__main__":
    run()
