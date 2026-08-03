"""``ss list`` - 列出小说/系列/章节。

只读命令：扫描文件系统（series/ 目录）和 JobRunner index，
不调用 LLM、不修改状态。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from cli._common import console, print_json

app = typer.Typer(
    name="list",
    help="列出小说 / 系列 / 章节",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command("series")
def list_series(
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """列出所有创作系列（扫 series/ 目录）。"""
    series_dir = Path("series")
    if not series_dir.exists():
        console.print("[dim]无 series/ 目录[/dim]")
        return
    items = []
    for d in sorted(series_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            variants = [v.name for v in d.iterdir() if v.is_dir() and v.name != "knowledge"]
            items.append({"name": d.name, "variants": len(variants), "has_bible": (d / "knowledge" / "series_bible.md").exists()})

    if fmt == "json":
        print_json(items)
        return

    table = Table(title=f"创作系列（{len(items)} 个）")
    table.add_column("系列名", style="cyan")
    table.add_column("变体数", justify="right")
    table.add_column("系列圣经")
    for it in items:
        table.add_row(it["name"], str(it["variants"]), "✅" if it["has_bible"] else "—")
    console.print(table)


@app.command("novels")
def list_novels(
    series: Optional[str] = typer.Option(None, "--series", "-s", help="按系列过滤"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """列出小说（后台 Job 或 series/ 下的变体）。"""
    # 优先从 JobRunner index 列出（后台生成的小说）
    from config import load_config
    from jobs import JobRunner
    cfg = load_config()
    runner = JobRunner(base_dir="jobs", cfg=cfg)
    jobs = runner.list()
    if series:
        # Job 没有 series 字段，按 project_name 模糊匹配
        jobs = [j for j in jobs if series in (j.project_name or "")]

    if fmt == "json":
        print_json([j.to_dict() for j in jobs])
        return

    if not jobs:
        console.print("[dim]📭 无小说。用 [bold]ss submit \"<需求>\"[/bold] 创建。[/dim]")
        return

    from cli._common import print_jobs_table
    print_jobs_table(jobs)


@app.command("chapters")
def list_chapters(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """列出某小说的所有章节。"""
    kd = _resolve_knowledge_dir(novel)
    if kd is None:
        console.print(f"[red]❌ 找不到小说 {novel}（既非 Job ID 也非有效路径）[/red]")
        raise typer.Exit(1)

    chap_dir = kd / "story" / "chapters"
    chapters = []
    if chap_dir.exists():
        for f in sorted(chap_dir.glob("chapter_*.md")):
            num = int(f.stem.split("_")[1])
            content = f.read_text(encoding="utf-8")
            chapters.append({
                "chapter": num,
                "title": _extract_title(content),
                "words": len(content),
                "path": str(f),
            })

    if fmt == "json":
        print_json(chapters)
        return

    if not chapters:
        console.print(f"[dim]无章节（{chap_dir}）[/dim]")
        return

    table = Table(title=f"章节列表（{len(chapters)} 章，{novel}）")
    table.add_column("章", justify="right", style="cyan")
    table.add_column("标题", overflow="fold")
    table.add_column("字数", justify="right")
    for c in chapters:
        table.add_row(str(c["chapter"]), c["title"] or "(无标题)", f"{c['words']:,}")
    console.print(table)


def _resolve_knowledge_dir(novel: str) -> Optional[Path]:
    """novel 参数 -> knowledge_dir Path。

    支持三种形式：Job ID、直接路径、series/<name>/variants/<v>。
    """
    # 1. 直接路径
    p = Path(novel)
    if p.exists() and (p / "story" / "chapters").exists():
        return p
    if (p / "knowledge").exists():
        return p / "knowledge"

    # 2. Job ID
    from config import load_config
    from jobs import JobRunner
    cfg = load_config()
    runner = JobRunner(base_dir="jobs", cfg=cfg)
    job = runner.get(novel)
    if job is not None and job.knowledge_dir:
        return Path(job.knowledge_dir)

    # 3. series/<name>/variants/<v>
    cand = Path("series") / novel
    if cand.exists() and (cand / "knowledge").exists():
        return cand / "knowledge"

    return None


def _extract_title(content: str) -> str:
    """从 markdown 章节内容提取标题（首个 # 行或首行）。"""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line:
            return line[:50]
    return ""
