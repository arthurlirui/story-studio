"""``ss run`` - 运行生成管线。

子命令：
- ``ss run pipeline``  长篇系列管线（直接调用 pipeline_core，无 sys.argv hack）
- ``ss run short``     短篇管线（直接调用 short_core，无 sys.argv hack）
- ``ss run stage``     单 phase（research/innovate/.../complete）
- ``ss run polish``    单章去AI化（deai polish）
- ``ss run batch``     批量并行写作
- ``ss run revise``    重写单章
- ``ss run style``     文学风格润色
- ``ss run multi-polish`` 多模型润色对比
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from cli._common import console, load_cfg, build_orch, create_llm_client

app = typer.Typer(
    name="run",
    help="运行生成管线",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command("pipeline")
def run_pipeline(
    task: Optional[str] = typer.Argument(None, help="taskfile 名（tasks/ 下，不含 .json）"),
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
    """长篇系列管线。

    读取 ``tasks/<task>.json``，按 variant 顺序执行 5-stage 管线
    （summaries -> polish_outline -> write_chapters -> deai -> export），
    支持断点续跑（.task_progress.json）。
    """
    if list_tasks:
        tasks_dir = Path("tasks")
        if tasks_dir.exists():
            for f in sorted(tasks_dir.glob("*.json")):
                console.print(f"  • {f.stem}")
        return

    if task is None:
        console.print("[red]❌ 请提供 taskfile 名（或用 --list 查看可用）[/red]")
        raise typer.Exit(1)

    # P0 修复：直接调用 pipeline_core 的结构化 API，不再 sys.argv hack
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(_run_pipeline_core(task, variant, stage, dry_run))


async def _run_pipeline_core(task: str, variant: str | None, stage: str | None, dry_run: bool):
    """直接调用 pipeline_core，替代 sys.argv hack。"""
    from cli.pipeline_core import run_pipeline as _run
    await _run(task, variant=variant, stage=stage, dry_run=dry_run)


@app.command("short")
def run_short(
    task: Optional[str] = typer.Argument(None, help="taskfile 名（tasks/short/ 下，不含 .json）"),
    stage: Optional[str] = typer.Option(
        None, "--stage", "-s",
        help="仅跑指定 stage（plan/write/deai）",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印计划不实际调用 LLM"),
    list_tasks: bool = typer.Option(False, "--list", "-l", help="列出可用短篇 taskfile"),
    batch: Optional[str] = typer.Option(None, "--batch", help="批量任务文件 (yaml/json)"),
) -> None:
    """短篇管线。plan -> write -> deai 三阶段。"""
    if list_tasks:
        from cli.short_core import list_short_tasks
        list_short_tasks()
        return

    if batch:
        import logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
        asyncio.run(_run_short_batch(batch))
        return

    if task is None:
        console.print("[red]❌ 请提供 taskfile 名（或用 --list 查看可用）[/red]")
        raise typer.Exit(1)

    # P0 修复：直接调用 short_core 的结构化 API，不再 sys.argv hack
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    asyncio.run(_run_short_core(task, stage, dry_run))


async def _run_short_core(task: str, stage: str | None, dry_run: bool):
    """直接调用 short_core，替代 sys.argv hack。"""
    from cli.short_core import run_short_task as _run
    await _run(task, target_stage=stage, dry_run=dry_run)


async def _run_short_batch(batch_file: str):
    """直接调用 short_core 批量，替代 sys.argv hack。"""
    from cli.short_core import run_short_batch as _run
    await _run(batch_file)


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
        cfg, orch, client = build_orch()
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
    """单章去AI化（deai polish）。"""

    async def _go():
        cfg, orch, client = build_orch()
        try:
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


@app.command("batch")
def run_batch(
    start: int = typer.Option(..., "--start", "-s", min=1, help="起始章节号"),
    count: int = typer.Option(3, "--count", "-c", min=1, max=20, help="批量章节数"),
) -> None:
    """批量并行写作（调用 phase_writing_batch）。"""

    async def _go():
        cfg, orch, client = build_orch()
        try:
            console.print(f"[cyan]🚀 批量写作: 第 {start}~{start + count - 1} 章（{count} 章并行）...[/cyan]")
            result = await orch.phase_writing_batch(start, count)
            console.print(f"[green]✅ 批量写作完成[/green]")
            console.print(result[:1500] if isinstance(result, str) else result)
        finally:
            await client.aclose()

    asyncio.run(_go())


@app.command("revise")
def run_revise(
    chapter: int = typer.Argument(..., min=1, help="要重写的章节号"),
) -> None:
    """重写单个章节（带自动修订循环）。"""

    async def _go():
        cfg, orch, client = build_orch()
        try:
            console.print(f"[cyan]✏️ 重写第 {chapter} 章...[/cyan]")
            result = await orch.phase_writing(chapter)
            console.print(f"[green]✅ 第 {chapter} 章重写完成[/green]")
            console.print(result[:1500] if isinstance(result, str) else result)
        finally:
            await client.aclose()

    asyncio.run(_go())


@app.command("style")
def run_style(
    chapter: int = typer.Argument(None, min=1, help="要润色的章节号"),
    style: str = typer.Option("moyan", "--style", "-s", help="风格名（如 moyan）"),
    list_styles: bool = typer.Option(False, "--list", "-l", help="列出可用风格后退出"),
) -> None:
    """文学风格润色（本地 Qwen + LoRA）。"""

    if list_styles:
        from agents.tools.style_polisher import STYLE_REGISTRY
        if not STYLE_REGISTRY:
            console.print("[dim]无可用风格[/dim]")
            return
        from rich.table import Table
        table = Table(title="🎨 可用风格")
        table.add_column("风格", style="cyan")
        table.add_column("名称")
        table.add_column("描述", overflow="fold")
        for key, info in STYLE_REGISTRY.items():
            table.add_row(key, info.get("name", ""), info.get("description", "")[:60])
        console.print(table)
        return

    if chapter is None:
        console.print("[red]❌ 请指定章节号（或用 --list 查看可用风格）[/red]")
        raise typer.Exit(1)

    async def _go():
        cfg, orch, client = build_orch()
        try:
            from pathlib import Path
            from agents.tools.style_polisher import STYLE_REGISTRY, create_style_polisher

            if style not in STYLE_REGISTRY:
                console.print(f"[red]❌ 未知风格 {style}，可用: {', '.join(STYLE_REGISTRY.keys())}[/red]")
                raise typer.Exit(1)

            kd = Path(cfg.knowledge_dir)
            chap_path = kd / "story" / "chapters" / f"chapter_{chapter:03d}.md"
            if not chap_path.exists():
                console.print(f"[red]❌ 章节不存在: {chap_path}[/red]")
                raise typer.Exit(1)

            console.print(f"[cyan]🎨 风格润色第 {chapter} 章（style={style}）...[/cyan]")
            polisher = create_style_polisher(style=style)
            content = chap_path.read_text(encoding="utf-8")
            polished = await polisher.polish(content, style=style)

            out_dir = kd / "output" / "styled"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"chapter_{chapter:03d}_{style}.md"
            out_file.write_text(polished, encoding="utf-8")
            console.print(f"[green]✅ 风格润色完成 -> {out_file}[/green]")
        finally:
            await client.aclose()

    asyncio.run(_go())


@app.command("multi-polish")
def run_multi_polish(
    chapter: Optional[int] = typer.Argument(None, min=1, help="要润色的章节号"),
    models: Optional[str] = typer.Option(
        None, "--models", "-m",
        help="逗号分隔的模型名，如 DeepSeek-V4-Pro,qwen-plus（缺省从配置读取）",
    ),
    file: Optional[str] = typer.Option(
        None, "--file", "-f",
        help="直接指定文件路径（与章节号二选一）",
    ),
    prompt_version: str = typer.Option(
        "v4", "--prompt-version", "-p",
        help="润色提示词版本 v1-v4",
    ),
    max_concurrent: int = typer.Option(
        3, "--max-concurrent", "-c", min=1, max=10,
        help="最大并发数",
    ),
) -> None:
    """多模型润色对比 — 用不同 LLM 同时润色，对比去 AI 效果。

    示例:
        ss run multi-polish 3 -m DeepSeek-V4-Pro,qwen-plus
        ss run multi-polish --file path/to/chapter.md -m glm-4,deepseek-chat
    """

    async def _go():
        cfg, orch, client = build_orch()
        try:
            # 解析模型列表
            if models:
                model_list = [m.strip() for m in models.split(",") if m.strip()]
            elif cfg.multi_polish.models:
                model_list = [m.name for m in cfg.multi_polish.models]
            else:
                console.print("[red]❌ 未指定模型，请用 --models 或在 settings.yaml 中配置 multi_polish.models[/red]")
                raise typer.Exit(1)

            if not model_list:
                console.print("[red]❌ 模型列表为空[/red]")
                raise typer.Exit(1)

            # 读取文本
            if file:
                file_path = Path(file)
                if not file_path.exists():
                    console.print(f"[red]❌ 文件不存在: {file}[/red]")
                    raise typer.Exit(1)
                content = file_path.read_text(encoding="utf-8")
                source_label = str(file_path)
            elif chapter:
                kd = Path(cfg.knowledge_dir)
                chap_path = kd / "story" / "chapters" / f"chapter_{chapter:03d}.md"
                if not chap_path.exists():
                    console.print(f"[red]❌ 章节不存在: {chap_path}[/red]")
                    raise typer.Exit(1)
                content = chap_path.read_text(encoding="utf-8")
                source_label = f"第{chapter}章"
            else:
                console.print("[red]❌ 请指定章节号或 --file[/red]")
                raise typer.Exit(1)

            console.print(f"[cyan]🔄 多模型润色对比: {source_label}[/cyan]")
            console.print(f"   模型: {', '.join(model_list)}")
            console.print(f"   并发数: {max_concurrent}")

            # 创建润色器
            from agents.tools.multi_polisher import create_multi_polisher

            prompt_file = Path(f"polish_prompt_{prompt_version}.txt")
            if not prompt_file.exists():
                prompt_file = Path("polish_prompt_v4.txt")

            polisher = create_multi_polisher(
                client=client,
                models=model_list,
                polish_prompt_path=str(prompt_file),
                max_concurrent=max_concurrent,
            )

            report = await polisher.polish(content)

            # ── Rich 表格输出 ──
            from rich.table import Table

            table = Table(title=f"📊 多模型润色对比 — {source_label}")
            table.add_column("排名", style="dim", width=5)
            table.add_column("模型", style="cyan")
            table.add_column("de-AI 评分", justify="center")
            table.add_column("评级", justify="center")
            table.add_column("字数", justify="right")
            table.add_column("耗时", justify="right")

            for i, r in enumerate(report.ranked_results, 1):
                if r.success:
                    score_color = "green" if r.deai_score >= 35 else "yellow" if r.deai_score >= 25 else "red"
                    table.add_row(
                        f"#{i}",
                        r.model_name,
                        f"[{score_color}]{r.deai_score}/50[/{score_color}]",
                        r.grade,
                        f"{r.word_count:,}",
                        f"{r.latency_ms:.0f}ms",
                    )
                else:
                    table.add_row(
                        f"#{i}",
                        r.model_name,
                        "—",
                        "[red]失败[/red]",
                        "—",
                        "—",
                    )

            console.print(table)

            # 保存结果
            kd = Path(cfg.knowledge_dir)
            out_dir = kd / "output" / "multi-polish"
            out_dir.mkdir(parents=True, exist_ok=True)

            if chapter:
                stem = f"chapter_{chapter:03d}"
            else:
                stem = Path(file).stem if file else "output"

            for r in report.results:
                if r.success:
                    safe_model = r.model_name.replace("/", "_").replace("\\", "_")
                    out_file = out_dir / f"{stem}_{safe_model}.md"
                    out_file.write_text(r.polished_text, encoding="utf-8")
                    console.print(f"  [dim]💾 {r.model_name} -> {out_file}[/dim]")

            # 保存对比报告
            report_path = out_dir / f"{stem}_report.md"
            report_path.write_text(report.summary, encoding="utf-8")
            console.print(f"  [dim]📋 报告 -> {report_path}[/dim]")

            console.print(f"[green]✅ 多模型润色完成[/green]")

        finally:
            await client.aclose()

    asyncio.run(_go())
