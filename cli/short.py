"""``ss short`` - 短篇生成与热榜。

子命令：
- ``ss short generate <prompt>``  生成短篇故事
- ``ss short trends``             热榜搜集 + 方向生成
- ``ss short genres``             列出可用 genre
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from cli._common import console, print_json, load_cfg, create_llm_client

app = typer.Typer(
    name="short",
    help="短篇生成与热榜（ShortStoryPipeline / TrendScout）",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command("generate")
def short_generate(
    prompt: str = typer.Argument(..., help="故事 prompt / 题材描述"),
    genre: str = typer.Option("urban", "--genre", "-g", help="genre 名（见 ss short genres）"),
    words: int = typer.Option(15000, "--words", "-w", min=1000, max=50000, help="目标字数"),
    pov: Optional[str] = typer.Option(None, "--pov", help="叙事视角（覆盖 genre 默认值）"),
    no_deai: bool = typer.Option(False, "--no-deai", help="跳过去AI化润色"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出目录（默认 short_output/<genre>_<timestamp>）"),
) -> None:
    """生成短篇故事（plan → write → deai 三阶段）。"""

    async def _go():
        cfg = load_cfg()
        from short_story.engine import ShortStoryPipeline, SkillConfigStore

        client = create_llm_client(cfg)
        try:
            skill_store = SkillConfigStore(Path("short_story/skill_configs"))
            if output is None:
                import time
                output_dir = Path("short_output") / f"{genre}_{int(time.time())}"
            else:
                output_dir = output
            output_dir.mkdir(parents=True, exist_ok=True)

            pipeline = ShortStoryPipeline(
                llm_client=client,
                skill_store=skill_store,
                knowledge_dir=output_dir,
                output_dir=output_dir,
            )

            console.print(f"[cyan]📝 生成短篇: genre={genre} words={words} deai={'off' if no_deai else 'on'}[/cyan]")
            console.print(f"  输出目录: {output_dir}")

            result = await pipeline.generate(
                genre=genre, prompt=prompt, word_count=words,
                enable_deai=not no_deai,
            )

            console.print(f"\n[green]✅ 生成完成[/green]")
            console.print(f"  标题: [bold]{result.title}[/bold]")
            console.print(f"  总字数: {result.total_words:,}")
            console.print(f"  耗时: {result.generation_time_s:.1f}s")
            console.print(f"  章节: {len(result.sections)} 节")
            console.print(f"  成品: {output_dir / 'story_final.md'}")
        finally:
            try:
                await client.aclose()
            except Exception:
                pass

    asyncio.run(_go())


@app.command("trends")
def short_trends(
    save: Optional[Path] = typer.Option(None, "--save", "-s", help="保存结果到指定目录"),
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="仅搜指定平台（逗号分隔）"),
) -> None:
    """热榜搜集 + 方向生成（TrendScout 全流程）。"""

    async def _go():
        cfg = load_cfg()
        from short_story.trend_scout import TrendScout, PLATFORM_QUERIES

        client = create_llm_client(cfg)
        try:
            scout = TrendScout(llm_client=client)

            queries = PLATFORM_QUERIES
            if platform:
                wanted = set(platform.split(","))
                queries = {k: v for k, v in PLATFORM_QUERIES.items() if k in wanted}

            console.print(f"[cyan]🔍 搜集 {len(queries)} 个平台热榜...[/cyan]")
            for name in queries:
                console.print(f"  • {name}")

            results = await scout.search_all_platforms()
            console.print(f"[green]✅ 搜索完成，分析中...[/green]")

            report = await scout.analyze_and_generate_directions(results)

            # 输出结果
            console.print(f"\n[bold cyan]📊 热榜分析报告[/bold cyan]")
            console.print(f"  搜索时间: {report.search_time}")
            console.print(f"  发现方向: {len(report.top_directions)} 个")
            console.print(f"  原始信号: {len(report.signals)} 条")

            from rich.table import Table
            table = Table(title="🎯 推荐方向")
            table.add_column("#", justify="right", style="cyan")
            table.add_column("方向", overflow="fold")
            table.add_column("热度", justify="right")
            table.add_column("品类")
            table.add_column("字数目标", justify="right")
            for i, d in enumerate(report.top_directions, 1):
                table.add_row(
                    str(i),
                    d.get("name", ""),
                    "🔥" * d.get("heat", 1),
                    d.get("genre", ""),
                    str(d.get("word_target", "")),
                )
            console.print(table)

            if save:
                save.mkdir(parents=True, exist_ok=True)
                (save / "trend_report.json").write_text(
                    json.dumps({
                        "search_results": results,
                        "directions": report.top_directions,
                        "signals": [s.__dict__ if hasattr(s, "__dict__") else s for s in report.signals],
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                console.print(f"[green]✅ 报告已保存到 {save / 'trend_report.json'}[/green]")
        finally:
            try:
                await client.aclose()
            except Exception:
                pass

    asyncio.run(_go())


@app.command("genres")
def short_genres(
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """列出可用的短篇 genre 配置。"""
    configs_dir = Path("short_story/skill_configs")
    if not configs_dir.exists():
        console.print("[dim]无 short_story/skill_configs/ 目录[/dim]")
        return

    genres = []
    for f in sorted(configs_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            genres.append({
                "name": f.stem,
                "genre": data.get("genre", f.stem),
                "category": data.get("category", ""),
                "default_pov": data.get("default_pov", ""),
                "word_range": data.get("word_range", {}),
                "section_target": data.get("section_target", 1500),
            })
        except json.JSONDecodeError:
            continue

    if fmt == "json":
        print_json(genres)
        return

    from rich.table import Table
    table = Table(title=f"📚 可用短篇 genre（{len(genres)} 个）")
    table.add_column("genre", style="cyan")
    table.add_column("品类")
    table.add_column("默认视角")
    table.add_column("字数范围")
    table.add_column("节目标字数", justify="right")
    for g in genres:
        wr = g.get("word_range", {})
        range_str = f"{wr.get('min', '?')}-{wr.get('max', '?')}" if wr else "-"
        table.add_row(g["name"], g.get("category", "-"), g.get("default_pov", "-"), range_str, str(g.get("section_target", "-")))
    console.print(table)
