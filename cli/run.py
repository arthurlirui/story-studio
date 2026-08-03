"""``ss run`` - 运行生成管线。

子命令：
- ``ss run pipeline``  替代 run_all.py（长篇系列任务，按 taskfile 跑多 variant + 5 stage）
- ``ss run short``     替代 run_short.py（短篇，plan -> write -> deai）
- ``ss run stage``     单 phase（research/innovate/.../complete）
- ``ss run polish``    单章去AI化（deai polish）
"""
from __future__ import annotations

import asyncio
from typing import Optional

import typer

from cli._common import console

app = typer.Typer(
    name="run",
    help="运行生成管线",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _load_cfg_and_orch():
    """懒加载 config + orchestrator + client。

    放在函数体内（而非模块顶层），避免 ``ss run --help`` 拉起重模块。
    """
    from config import load_config
    from agents.llm_client import init_client
    from orchestrator import StoryOrchestrator

    cfg = load_config()
    client = init_client(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)
    orch = StoryOrchestrator(cfg, client=client)
    return cfg, orch, client


@app.command("pipeline")
def run_pipeline(
    task: str = typer.Argument(..., help="taskfile 名（tasks/ 下，不含 .json）"),
    variant: Optional[str] = typer.Option(
        None, "--variant", "-V",
        help="仅跑指定 variant（逗号分隔，如 01,03），缺省跑全部",
    ),
    stage: Optional[str] = typer.Option(
        None, "--stage", "-s",
        help="仅跑指定 stage（summaries/polish_outline/write_chapters/deai/export）",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印计划不实际调用 LLM"),
    list_tasks: bool = typer.Option(False, "--list", "-l", help="列出可用 taskfile 后退出"),
) -> None:
    """长篇系列管线（替代 run_all.py）。

    读取 ``tasks/<task>.json``，按 variant 顺序执行 5-stage 管线
    （summaries -> polish_outline -> write_chapters -> deai -> export），
    支持断点续跑（.task_progress.json）。
    """
    if list_tasks:
        from pathlib import Path
        tasks_dir = Path("tasks")
        if tasks_dir.exists():
            for f in sorted(tasks_dir.glob("*.json")):
                console.print(f"  • {f.stem}")
        return

    async def _go():
        # 复用现有 run_all.py 逻辑：直接调其 main 入口
        import run_all as _run_all
        argv = [task]
        if variant:
            argv += ["--variant", variant]
        if stage:
            argv += ["--stage", stage]
        if dry_run:
            argv += ["--dry-run"]
        # run_all.py 用 argparse 解析 sys.argv，这里临时替换
        import sys
        old = sys.argv
        sys.argv = ["run_all.py"] + argv
        try:
            await _run_all.async_main() if hasattr(_run_all, "async_main") else _run_all.main()
        finally:
            sys.argv = old

    try:
        asyncio.run(_go())
    except AttributeError:
        # run_all.main 不是 async，直接同步调用
        console.print("[yellow]注意：run_all.py 未提供 async_main，将同步执行[/yellow]")
        import run_all as _run_all
        argv = [task]
        if variant:
            argv += ["--variant", variant]
        if stage:
            argv += ["--stage", stage]
        if dry_run:
            argv += ["--dry-run"]
        import sys
        old = sys.argv
        sys.argv = ["run_all.py"] + argv
        try:
            _run_all.main()
        finally:
            sys.argv = old


@app.command("short")
def run_short(
    task: str = typer.Argument(..., help="taskfile 名（tasks/short/ 下，不含 .json）"),
    stage: Optional[str] = typer.Option(
        None, "--stage", "-s",
        help="仅跑指定 stage（plan/write/deai）",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印计划不实际调用 LLM"),
    list_tasks: bool = typer.Option(False, "--list", "-l", help="列出可用短篇 taskfile"),
) -> None:
    """短篇管线（替代 run_short.py）。plan -> write -> deai 三阶段。"""
    if list_tasks:
        from pathlib import Path
        d = Path("tasks/short")
        if d.exists():
            for f in sorted(d.glob("*.json")):
                console.print(f"  • {f.stem}")
        return

    import sys
    argv = ["run_short.py", task]
    if stage:
        argv += ["--stage", stage]
    if dry_run:
        argv += ["--dry-run"]
    old = sys.argv
    sys.argv = argv
    try:
        import run_short
        run_short.main()
    finally:
        sys.argv = old


@app.command("stage")
def run_stage(
    phase: str = typer.Argument(
        ..., help="phase 名：research/innovate/planning/building/outlining/writing/complete",
    ),
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c", help="写作章节号（仅 writing）"),
) -> None:
    """执行单个 phase（交互式 /next 的命令行版本）。"""

    valid = {"research", "innovate", "planning", "building", "outlining",
             "writing", "complete"}
    if phase not in valid:
        raise typer.BadParameter(f"未知 phase: {phase}，可选: {', '.join(sorted(valid))}")

    async def _go():
        cfg, orch, client = _load_cfg_and_orch()
        try:
            method = getattr(orch, f"phase_{phase}", None)
            if method is None:
                console.print(f"[red]❌ orchestrator 无 phase_{phase} 方法[/red]")
                raise typer.Exit(1)
            if phase == "writing" and chapter is not None:
                result = await method(chapter)
            elif phase == "planning":
                result = await method(orch.project_name or "")
            elif phase in ("research", "innovate"):
                result = await method(orch.project_name or "")
            else:
                result = await method()
            console.print(f"[green]✅ phase_{phase} 完成[/green]")
            console.print(result[:1500] if isinstance(result, str) else result)
        finally:
            await client.aclose()

    asyncio.run(_go())


@app.command("polish")
def run_polish(
    chapter: int = typer.Argument(..., min=1, help="章节号"),
    prompt_version: str = typer.Option("v4", "--prompt-version", "-p", help="polish prompt 版本 v1-v4"),
) -> None:
    """单章去AI化（deai polish）。

    用 polish_prompt_v4.txt（可指定 v1-v3）对指定章节做去AI化润色，
    输出到 output/polished/chapter_NNN.md。
    """

    async def _go():
        cfg, orch, client = _load_cfg_and_orch()
        try:
            # 复用 run_all.run_deai 的核心逻辑
            import run_all
            from pathlib import Path

            # 选择 prompt 文件
            prompt_file = Path(f"polish_prompt_{prompt_version}.txt")
            if not prompt_file.exists():
                prompt_file = Path("polish_prompt_v4.txt")
            if not prompt_file.exists():
                console.print("[red]❌ 找不到 polish_prompt 文件[/red]")
                raise typer.Exit(1)

            from agents.knowledge import KnowledgeStore
            kd = Path(cfg.knowledge_dir)
            chap_path = kd / "story" / "chapters" / f"chapter_{chapter:03d}.md"
            if not chap_path.exists():
                console.print(f"[red]❌ 章节不存在: {chap_path}[/red]")
                raise typer.Exit(1)

            console.print(f"[cyan]🔄 去AI化第 {chapter} 章（prompt={prompt_file.name}）...[/cyan]")
            # 直接调 orchestrator 的 client 做 polish（与 run_all.run_deai 同逻辑）
            template = prompt_file.read_text(encoding="utf-8")
            content = chap_path.read_text(encoding="utf-8")
            polished = await client.chat(
                messages=[{"role": "user", "content": content}],
                system=template,
                temperature=0.82,
                max_tokens=12000,
            )
            out_dir = kd / "output" / "polished"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"chapter_{chapter:03d}.md").write_text(polished, encoding="utf-8")
            (out_dir / f"chapter_{chapter:03d}.txt").write_text(polished, encoding="utf-8")
            console.print(f"[green]✅ 已润色 -> {out_dir / f'chapter_{chapter:03d}.md'}[/green]")
        finally:
            await client.aclose()

    asyncio.run(_go())
