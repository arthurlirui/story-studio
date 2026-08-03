"""``ss export`` - 导出成品。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from cli._common import console
from cli.novels import _resolve_knowledge_dir

app = typer.Typer(
    name="export",
    help="导出成品（final / covers）",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command("final")
def export_final(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    fmt: str = typer.Option("md", "--format", "-f", help="输出格式：md | txt"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="输出文件路径（缺省输出到 stdout）"),
) -> None:
    """合并所有章节为最终成品。

    优先用 output/polished/ 下已去AI化的章节，无则用原始 chapters/。
    """
    kd = _resolve_knowledge_dir(novel)
    if kd is None:
        console.print(f"[red]❌ 找不到小说 {novel}[/red]")
        raise typer.Exit(1)

    polished_dir = kd / "output" / "polished"
    chap_dir = kd / "story" / "chapters"
    src = polished_dir if polished_dir.exists() else chap_dir
    if not src.exists():
        console.print(f"[red]❌ 无章节目录: {src}[/red]")
        raise typer.Exit(1)

    parts = []
    for f in sorted(src.glob("chapter_*.md")) + sorted(src.glob("chapter_*.txt")):
        parts.append(f.read_text(encoding="utf-8"))

    if not parts:
        console.print(f"[dim]无章节可导出（{src}）[/dim]")
        return

    merged = "\n\n---\n\n".join(parts)
    # txt 格式去掉 markdown 标记
    if fmt == "txt":
        from agents.text_cleaner import clean_chapter_body
        merged = "\n\n---\n\n".join(clean_chapter_body(p) for p in parts)

    if out:
        out.write_text(merged, encoding="utf-8")
        console.print(f"[green]✅ 已导出 {len(parts)} 章到 {out}[/green]")
    else:
        console.print(merged)


@app.command("covers")
def export_covers(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
) -> None:
    """导出封面设计 brief（cover_brief.json + cover_prompt.txt）。

    注意：当前仅生成 brief 文本，真实渲染需 ComfyUI（见 tools/book_cover_comfy.py）。
    """
    kd = _resolve_knowledge_dir(novel)
    if kd is None:
        console.print(f"[red]❌ 找不到小说 {novel}[/red]")
        raise typer.Exit(1)

    cover_dir = kd / "output" / "covers"
    brief = cover_dir / "cover_brief.json" if cover_dir.exists() else None
    prompt = cover_dir / "cover_prompt.txt" if cover_dir.exists() else None

    if brief and brief.exists():
        console.print(f"[green]封面 brief:[/green] {brief}")
        console.print(brief.read_text(encoding="utf-8"))
    else:
        console.print("[dim]无 cover_brief.json（需先跑完 phase_complete 生成）[/dim]")
    if prompt and prompt.exists():
        console.print(f"\n[green]封面英文 prompt:[/green] {prompt}")
        console.print(prompt.read_text(encoding="utf-8"))
