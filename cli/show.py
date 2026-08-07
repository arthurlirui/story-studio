"""``ss show`` - 知识库读取（只读）。

对应 API 的 knowledge 路由：outline / world / characters / chapter / cost / quality / research。
全部支持 ``--format json`` 机器可读输出。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from cli._common import (
    console,
    print_json,
    build_knowledge_store,
    print_world_table,
    print_characters_table,
    print_cost_table,
    print_quality_table,
)

app = typer.Typer(
    name="show",
    help="查看知识库内容（大纲/世界观/角色/章节/用量/质量/调研）",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _fail(novel: str) -> None:
    console.print(f"[red]❌ 找不到小说 {novel}（既非 Job ID 也非有效路径）[/red]")
    raise typer.Exit(1)


@app.command("outline")
def show_outline(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    fmt: str = typer.Option("text", "--format", "-f", help="text | json"),
) -> None:
    """查看大纲全文。"""
    kd, ks = build_knowledge_store(novel)
    if kd is None:
        _fail(novel)
    outline = ks.load_outline()
    if not outline:
        console.print(f"[dim]无大纲（{kd}）[/dim]")
        return
    if fmt == "json":
        print_json({"outline": outline})
    else:
        console.print(outline)


@app.command("world")
def show_world(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    doc: Optional[str] = typer.Option(None, "--doc", "-d", help="指定文档名查看单篇"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """查看世界观文档列表或单篇。"""
    kd, ks = build_knowledge_store(novel)
    if kd is None:
        _fail(novel)

    if doc:
        content = ks.load_world(doc)
        if not content:
            console.print(f"[red]❌ 文档不存在: {doc}[/red]")
            raise typer.Exit(1)
        if fmt == "json":
            print_json({"doc": doc, "content": content})
        else:
            console.print(content)
        return

    docs = ks.list_world_docs()
    summary = ks.get_world_summary() if hasattr(ks, "get_world_summary") else ""
    if fmt == "json":
        print_json({"docs": docs, "summary": summary})
    else:
        print_world_table(docs, summary)


@app.command("characters")
def show_characters(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="指定角色名查看单篇"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """查看角色档案列表或单篇。"""
    kd, ks = build_knowledge_store(novel)
    if kd is None:
        _fail(novel)

    if name:
        content = ks.load_character(name)
        if not content:
            console.print(f"[red]❌ 角色不存在: {name}[/red]")
            raise typer.Exit(1)
        if fmt == "json":
            print_json({"name": name, "content": content})
        else:
            console.print(content)
        return

    chars = ks.list_characters()
    # 获取摘要
    char_list = []
    for c in chars:
        summary_data = ks.get_all_character_summaries() if hasattr(ks, "get_all_character_summaries") else {}
        char_list.append({"name": c, "summary": summary_data.get(c, "")[:80] if isinstance(summary_data, dict) else ""})

    if fmt == "json":
        print_json(char_list)
    else:
        print_characters_table(char_list)


@app.command("chapter")
def show_chapter(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    num: int = typer.Argument(..., min=1, help="章节号"),
    fmt: str = typer.Option("text", "--format", "-f", help="text | json"),
) -> None:
    """查看单章正文。"""
    kd, ks = build_knowledge_store(novel)
    if kd is None:
        _fail(novel)
    content = ks.load_chapter(num)
    if not content:
        console.print(f"[red]❌ 第 {num} 章不存在[/red]")
        raise typer.Exit(1)
    if fmt == "json":
        print_json({"chapter": num, "content": content})
    else:
        console.print(content)


@app.command("cost")
def show_cost(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """查看 token 用量分模型统计。"""
    kd, _ = build_knowledge_store(novel)
    if kd is None:
        _fail(novel)

    from orchestrator_state import RunState
    state_path = kd / "run_state.json"
    if not state_path.exists():
        console.print(f"[dim]无 run_state.json（{kd}）[/dim]")
        return
    state = RunState.load(state_path)
    cost = state.cost_summary()

    if fmt == "json":
        print_json(cost)
    else:
        print_cost_table(cost)


@app.command("quality")
def show_quality(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """查去看AI化质量面板（每章评分 + verdict）。"""
    kd, ks = build_knowledge_store(novel)
    if kd is None:
        _fail(novel)

    reviews_dir = kd / "story" / "reviews"
    summaries_dir = kd / "story" / "summaries"

    chapters = []
    pass_count = revise_count = reject_count = 0

    # 扫描 reviews 目录获取 verdict + deai_score
    if reviews_dir.exists():
        for f in sorted(reviews_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                ch_num = data.get("chapter", int(f.stem.split("_")[1]) if "_" in f.stem else 0)
                verdict = data.get("verdict", data.get("result", "-"))
                score = data.get("deai_score", data.get("score", "-"))
                title = data.get("title", "")
                chapters.append({"chapter": ch_num, "title": title, "verdict": verdict, "deai_score": score})
                if verdict == "PASS":
                    pass_count += 1
                elif verdict == "REVISE":
                    revise_count += 1
                elif verdict == "REJECT":
                    reject_count += 1
            except (json.JSONDecodeError, ValueError, IndexError):
                continue

    # 如果没有 reviews，从 summaries 目录推断
    if not chapters and summaries_dir.exists():
        for f in sorted(summaries_dir.glob("chapter_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                ch_num = int(f.stem.split("_")[1])
                score = data.get("deai_score", data.get("score", "-"))
                verdict = data.get("verdict", "PASS" if isinstance(score, (int, float)) and score < 30 else "-")
                chapters.append({"chapter": ch_num, "title": data.get("title", ""), "verdict": verdict, "deai_score": score})
            except (json.JSONDecodeError, ValueError, IndexError):
                continue

    result = {
        "chapters": chapters,
        "summary": {"pass": pass_count, "revise": revise_count, "reject": reject_count},
    }

    if fmt == "json":
        print_json(result)
    else:
        if not chapters:
            console.print(f"[dim]无质量数据（{kd}）[/dim]")
            return
        print_quality_table(result)


@app.command("research")
def show_research(
    novel: str = typer.Argument(..., help="Job ID 或 knowledge_dir 路径"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="指定主题查看单篇"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """查看调研资料列表或单篇。"""
    kd, ks = build_knowledge_store(novel)
    if kd is None:
        _fail(novel)

    if topic:
        content = ks.load_research(topic)
        if not content:
            console.print(f"[red]❌ 主题不存在: {topic}[/red]")
            raise typer.Exit(1)
        if fmt == "json":
            print_json({"topic": topic, "content": content})
        else:
            console.print(content)
        return

    topics = ks.list_research_topics()
    if fmt == "json":
        print_json({"topics": topics})
    else:
        from rich.table import Table
        table = Table(title=f"🔍 调研主题（{len(topics)} 个）")
        table.add_column("主题", style="cyan", overflow="fold")
        for t in topics:
            table.add_row(t if isinstance(t, str) else str(t))
        console.print(table)
