"""CLI 共享工具：Rich Console 单例、表格/进度 helper、状态图标。

集中所有输出格式化逻辑，子命令模块只调用这里的函数，避免每个文件
各自 ``from rich import ...`` 并重复排版代码。
"""
from __future__ import annotations

import json as _json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

# 单例 Console：所有 CLI 输出走同一实例，统一 stderr/stdout 策略。
console = Console()
err_console = Console(stderr=True)

# Job / Task 状态 -> 图标 + 颜色样式
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "queued":      ("⏳", "yellow"),
    "running":     ("🔄", "cyan"),
    "succeeded":   ("✅", "green"),
    "done":        ("✅", "green"),
    "failed":      ("❌", "red"),
    "cancelled":   ("🚫", "magenta"),
    "recoverable": ("⚠️", "yellow"),
    "pending":     ("⏳", "white"),
    "skipped":     ("⏭️", "dim"),
}

# 7-phase 中文描述
PHASE_LABEL: dict[str, str] = {
    "idle":      "待启动",
    "research":  "调研",
    "innovate":  "创新亮点",
    "planning":  "策划",
    "building":  "设定",
    "outlining": "大纲",
    "writing":   "写作",
    "complete":  "完稿",
}


def status_icon(status: str) -> str:
    """返回带图标的单字符状态标记。"""
    return STATUS_STYLE.get(status, ("❓", "white"))[0]


def status_style(status: str) -> str:
    """返回状态对应的 Rich 颜色样式名。"""
    return STATUS_STYLE.get(status, ("❓", "white"))[1]


def phase_label(phase: str) -> str:
    """phase 英文 -> 中文，未知原样返回。"""
    return PHASE_LABEL.get(phase, phase)


def print_json(data: Any) -> None:
    """机器可读 JSON 输出（--format json 用）。写到 stdout。"""
    sys.stdout.write(_json.dumps(data, ensure_ascii=False, indent=2, default=str))
    sys.stdout.write("\n")


def print_jobs_table(jobs: list[Any]) -> None:
    """渲染 Job 列表为 Rich 表格。"""
    table = Table(title=f"后台 Job（{len(jobs)} 个）", show_lines=False)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("状态")
    table.add_column("阶段")
    table.add_column("进度", justify="right")
    table.add_column("项目", overflow="fold")

    for j in jobs:
        prog = _format_job_progress(j)
        table.add_row(
            j.id,
            f"[{status_style(j.status)}]{status_icon(j.status)} {j.status}[/{status_style(j.status)}]",
            phase_label(j.phase),
            prog,
            j.project_name or "(未命名)",
        )
    console.print(table)


def _format_job_progress(j: Any) -> str:
    """区分任务粒度 vs 章节粒度进度（与 main.py._format_job_progress 一致）。"""
    if not j.progress or not j.progress[1]:
        return "-"
    if j.phase == "writing":
        return f"chapters:{j.progress[0]}/{j.progress[1]}"
    if j.task_progress and j.task_progress[1]:
        return f"tasks:{j.task_progress[0]}/{j.task_progress[1]}"
    return f"{j.progress[0]}/{j.progress[1]}"


def print_status_panel(status: dict) -> None:
    """渲染 orchestrator.get_status() 返回的 dict 为面板。"""
    project = status.get("project") or "(未创建)"
    phase = phase_label(status.get("phase", "idle"))
    chapters = f"{status.get('chapters_written', 0)}/{status.get('total_chapters') or '?'}"
    body = (
        f"[bold]项目[/bold]: {project}\n"
        f"[bold]阶段[/bold]: {phase}\n"
        f"[bold]章节[/bold]: {chapters}\n"
        f"[bold]世界观文档[/bold]: {len(status.get('world_docs', []))} 个\n"
        f"[bold]角色档案[/bold]: {len(status.get('characters', []))} 个\n"
        f"[bold]Agent 团队[/bold]: {len(status.get('agents', []))} 人\n"
        f"[bold]主力模型[/bold]: {status.get('model', '-')}\n"
        f"[bold]轻量模型[/bold]: {status.get('light_model', '-')}"
    )
    console.print(Panel(body, title="📊 Story Studio 状态", border_style="cyan"))

    cost = status.get("cost")
    if cost and cost.get("total_calls"):
        console.print(
            f"  累计: {cost['total_calls']} 次调用 / "
            f"{cost['total_tokens']:,} tokens"
        )


def print_agent_tree(agents: list[dict]) -> None:
    """渲染智能体团队为 Rich 树（按 main/light tier 分组）。

    tier 判定依据 _agent_model 的路由规则：main tier 的 role 名匹配
    showrunner/world architect/character designer/character psychologist/
    scene writer/innovator，其余为 light tier。
    """
    tree = Tree("🤖 [bold cyan]创作团队[/bold cyan]")
    main_branch = tree.add("[bold]main tier[/bold]（主力模型）")
    light_branch = tree.add("[bold]light tier[/bold]（轻量模型）")

    # main tier 的 role 显示名（与 orchestrator.py 实例化时的第二参数一致）
    main_roles = {
        "Showrunner", "World Architect", "Character Designer",
        "Character Psychologist", "Scene Writer", "Innovator",
    }
    for a in agents:
        label = f"{a.get('name', '?')} [dim]({a.get('role', '?')})[/dim] - {a.get('description', '')[:40]}"
        label += f"  [italic]model={a.get('model', '?')}[/italic]"
        if a.get("role") in main_roles:
            main_branch.add(label)
        else:
            light_branch.add(label)
    console.print(tree)


def print_tasks_table(tasks: list[Any]) -> None:
    """渲染 TaskPlanner 任务清单。"""
    table = Table(title="📋 任务清单", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("状态")
    table.add_column("阶段")
    table.add_column("名称", overflow="fold")
    table.add_column("结果/错误", overflow="fold")

    for t in tasks:
        st = getattr(t, "status", str(t.get("status", "")))
        icon = status_icon(st)
        excerpt = getattr(t, "result_excerpt", "") or t.get("result_excerpt", "")
        error = getattr(t, "error", "") or t.get("error", "")
        detail = (excerpt or error or "")[:60]
        table.add_row(
            str(getattr(t, "id", t.get("id", ""))),
            f"[{status_style(st)}]{icon} {st}[/{status_style(st)}]",
            phase_label(getattr(t, "phase", t.get("phase", ""))),
            getattr(t, "name", t.get("name", "")),
            detail,
        )
    console.print(table)


def mask_secret(value: str, visible: int = 4) -> str:
    """密钥脱敏：保留前 visible 位，其余用 * 替代。"""
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "*" * (len(value) - visible)


# ── 统一辅助函数 ──────────────────────────────────────────────
# 所有子命令通过这些函数获取 config / runner / orchestrator，
# 避免各文件重复 ``load_config()`` + ``init_client()`` + ``StoryOrchestrator()``
# 三件套，并确保 ``--config`` 全局选项一致生效。


def load_cfg():
    """加载配置，尊重 ``--config`` 全局选项。

    ``cli_state["config_path"]`` 存的是 settings.yaml 文件路径，
    而 ``load_config`` 接收的是目录，故取其父目录。
    """
    from config import load_config
    from cli.main import cli_state
    cp = cli_state.get("config_path")
    if cp:
        from pathlib import Path
        return load_config(str(Path(cp).parent))
    return load_config()


def get_runner():
    """构造 JobRunner（base_dir=jobs），配置走 load_cfg()。"""
    from jobs import JobRunner
    return JobRunner(base_dir="jobs", cfg=load_cfg())


def build_orch():
    """加载配置 + 初始化 LLMClient + 构造 StoryOrchestrator。

    返回 (cfg, orch, client)。调用方负责 ``await client.aclose()``。
    """
    from agents.llm_client import init_client
    from orchestrator import StoryOrchestrator
    cfg = load_cfg()
    client = init_client(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)
    orch = StoryOrchestrator(cfg, client=client)
    return cfg, orch, client


def resolve_novel_kd(novel: str):
    """novel 参数 -> knowledge_dir 路径（统一入口）。

    支持三种形式：Job ID、直接路径、series/<name>/variants/<v>。
    返回 Path 或 None。供 show / export 等命令复用。
    """
    from cli.novels import _resolve_knowledge_dir
    return _resolve_knowledge_dir(novel)


def build_knowledge_store(novel: str):
    """为指定 novel 构造 KnowledgeStore。

    返回 (kd_path, knowledge_store) 或 (None, None)。
    """
    from agents.knowledge import create_knowledge_store
    kd = resolve_novel_kd(novel)
    if kd is None:
        return None, None
    ks = create_knowledge_store(str(kd), None, None)
    return kd, ks


# ── 知识库渲染 helper ──────────────────────────────────────────


def print_world_table(docs: list[dict], summary: str = "") -> None:
    """渲染世界观文档列表。"""
    table = Table(title=f"🌍 世界观文档（{len(docs)} 个）")
    table.add_column("文档", style="cyan", overflow="fold")
    table.add_column("摘要", overflow="fold")
    for d in docs:
        table.add_row(d.get("name", d.get("doc", "?")), d.get("summary", d.get("preview", ""))[:80])
    console.print(table)
    if summary:
        console.print(f"\n[bold]总览[/bold]: {summary[:500]}")


def print_characters_table(characters: list[dict]) -> None:
    """渲染角色档案列表。"""
    table = Table(title=f"👤 角色档案（{len(characters)} 个）")
    table.add_column("角色", style="cyan")
    table.add_column("摘要", overflow="fold")
    for c in characters:
        table.add_row(c.get("name", c.get("character", "?")), c.get("summary", c.get("preview", ""))[:80])
    console.print(table)


def print_cost_table(cost: dict) -> None:
    """渲染 token 用量分模型统计。"""
    table = Table(title="💰 Token 用量")
    table.add_column("模型", style="cyan")
    table.add_column("调用数", justify="right")
    table.add_column("输入 tokens", justify="right")
    table.add_column("输出 tokens", justify="right")
    table.add_column("总计", justify="right")
    for model, stat in cost.get("models", cost).items():
        if isinstance(stat, dict):
            table.add_row(
                model,
                str(stat.get("calls", stat.get("total_calls", "-"))),
                f"{stat.get('prompt_tokens', stat.get('input_tokens', 0)):,}",
                f"{stat.get('completion_tokens', stat.get('output_tokens', 0)):,}",
                f"{stat.get('total_tokens', 0):,}",
            )
    console.print(table)
    if cost.get("total_tokens"):
        console.print(f"\n[bold]合计[/bold]: {cost['total_tokens']:,} tokens / {cost.get('total_calls', 0)} 次调用")


def print_quality_table(quality: dict) -> None:
    """渲染 deai 质量面板（每章评分 + verdict）。"""
    chapters = quality.get("chapters", [])
    table = Table(title=f"📊 去AI化质量（{len(chapters)} 章）")
    table.add_column("章", justify="right", style="cyan")
    table.add_column("标题", overflow="fold")
    table.add_column("评分", justify="right")
    table.add_column("判定")
    for c in chapters:
        verdict = c.get("verdict", "-")
        score = c.get("deai_score", c.get("score", "-"))
        vstyle = {"PASS": "green", "REVISE": "yellow", "REJECT": "red"}.get(verdict, "white")
        table.add_row(
            str(c.get("chapter", "?")),
            c.get("title", "(无标题)")[:40],
            str(score),
            f"[{vstyle}]{verdict}[/{vstyle}]",
        )
    console.print(table)

    summary = quality.get("summary", {})
    if summary:
        console.print(
            f"\n[bold]汇总[/bold]: "
            f"✅ PASS {summary.get('pass', 0)}  "
            f"⚠️ REVISE {summary.get('revise', 0)}  "
            f"❌ REJECT {summary.get('reject', 0)}"
        )
