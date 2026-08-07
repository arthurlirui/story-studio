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
    from cli._common import get_runner
    runner = get_runner()
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
    novel: str = typer.Argument(..., help="Job ID 或变体路径"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """列出某小说的所有章节。"""
    resolved = _resolve_novel(novel)
    if resolved is None:
        console.print(f"[red]❌ 找不到小说 {novel}（既非 Job ID 也非有效路径）[/red]")
        raise typer.Exit(1)

    chapters = _scan_chapters(resolved)

    if fmt == "json":
        print_json(chapters)
        return

    if not chapters:
        console.print(f"[dim]无章节文件（搜索于 {resolved}）[/dim]")
        return

    table = Table(title=f"章节列表（{len(chapters)} 章，{novel}）")
    table.add_column("章", justify="right", style="cyan")
    table.add_column("标题", overflow="fold")
    table.add_column("字数", justify="right")
    for c in chapters:
        table.add_row(str(c["chapter"]), c["title"] or "(无标题)", f"{c['words']:,}")
    console.print(table)


def _resolve_novel(novel: str) -> Optional[Path]:
    """novel 参数 -> 基准路径（变体根目录或 knowledge_dir）。

    支持三种形式：Job ID、直接路径、series/<name>/variants/<v>。
    返回后可被 _scan_chapters 在其中搜索章节文件。
    """
    # 1. 直接路径
    p = Path(novel)
    if p.exists() and (p.is_dir()):
        # knowledge_dir 直接命中（含 story/chapters）
        if (p / "story" / "chapters").exists():
            return p
        # 变体根（含 knowledge/ 子目录）
        if (p / "knowledge").exists():
            return p / "knowledge"
        # 变体根（扁平布局：直接含 polished/ 或 chN.md）
        if (p / "polished").exists() or any(p.glob("ch*.md")):
            return p
        # 系列根（含 variants/ 子目录 -> 递归扫各变体）
        if (p / "variants").exists():
            return p

    # 2. Job ID
    from cli._common import get_runner
    runner = get_runner()
    job = runner.get(novel)
    if job is not None and job.knowledge_dir:
        return Path(job.knowledge_dir)

    # 3. series/<name>/variants/<v>
    cand = Path("series") / novel
    if cand.exists():
        if (cand / "knowledge").exists():
            return cand / "knowledge"
        if (cand / "polished").exists() or list(cand.glob("ch*.md")):
            return cand

    # 4. series/<name>（系列根，扫所有变体）
    if cand.exists():
        return cand

    return None


def _scan_chapters(base: Path) -> list[dict]:
    """在 base 下搜索章节文件，兼容多种布局。

    布局优先级：
    1. story/chapters/chapter_NNN.md（标准 orchestrator 布局）
    2. output/polished/chapter_NNN.md（去AI化产物）
    3. polished/chapter_NNN.md（扁平变体布局）
    4. chN.md / chNN.md（旧 campaign 布局，哥伦布计划等）
    """
    chapters: list[dict] = []

    # 1. story/chapters/chapter_*.md
    chap_dir = base / "story" / "chapters"
    if chap_dir.exists():
        for f in sorted(chap_dir.glob("chapter_*.md")):
            num = int(f.stem.split("_")[1])
            content = f.read_text(encoding="utf-8")
            chapters.append({"chapter": num, "title": _extract_title(content),
                             "words": len(content), "path": str(f)})

    # 2-3. polished/chapter_*.md（output/polished 或扁平 polished）
    if not chapters:
        for sub in ("output/polished", "polished"):
            pd = base / sub
            if pd.exists():
                for f in sorted(pd.glob("chapter_*.md")) + sorted(pd.glob("chapter_*.txt")):
                    num = int(f.stem.split("_")[1])
                    content = f.read_text(encoding="utf-8")
                    chapters.append({"chapter": num, "title": _extract_title(content),
                                     "words": len(content), "path": str(f)})
                if chapters:
                    break

    # 4. chN.md / chNN.md（旧布局）
    if not chapters:
        for f in sorted(base.glob("ch*.md")):
            stem = f.stem
            num_str = "".join(c for c in stem if c.isdigit())
            if num_str:
                num = int(num_str)
                content = f.read_text(encoding="utf-8")
                chapters.append({"chapter": num, "title": _extract_title(content),
                                 "words": len(content), "path": str(f)})

    # 若 base 是系列根（含 variants/），递归扫各变体
    if not chapters and (base / "variants").exists():
        for v in sorted((base / "variants").iterdir()):
            if v.is_dir():
                sub_chapters = _scan_chapters(v)
                for c in sub_chapters:
                    c["variant"] = v.name
                chapters.extend(sub_chapters)

    return chapters


def _resolve_knowledge_dir(novel: str) -> Optional[Path]:
    """novel -> knowledge_dir（向后兼容，export 命令用）。

    与 _resolve_novel 的区别：返回的路径保证是 knowledge_dir（含 story/chapters），
    或扁平变体根。export 等需要写 output/ 的命令用这个。
    """
    resolved = _resolve_novel(novel)
    if resolved is None:
        return None
    # 若返回的是变体根且含 knowledge/，取 knowledge/
    if (resolved / "knowledge" / "story").exists():
        return resolved / "knowledge"
    return resolved


def _extract_title(content: str) -> str:
    """从 markdown 章节内容提取标题（首个 # 行或首行）。"""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line:
            return line[:50]
    return ""
