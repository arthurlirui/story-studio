"""``ss agents`` - 智能体团队信息。"""
from __future__ import annotations

import typer

from cli._common import console, print_agent_tree

app = typer.Typer(
    name="agents",
    help="智能体团队信息",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _build_orch():
    """懒加载 orchestrator 以读取 agents 注册表。"""
    from config import load_config
    from agents.llm_client import init_client
    from orchestrator import StoryOrchestrator
    cfg = load_config()
    client = init_client(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)
    return StoryOrchestrator(cfg, client=client)


@app.command("list")
def agents_list() -> None:
    """列出所有智能体（按 main/light tier 分组的树形图）。"""
    orch = _build_orch()
    agents = [a.to_dict() for a in orch.agents.values()]
    print_agent_tree(agents)


@app.command("inspect")
def agents_inspect(
    name: str = typer.Argument(..., help="智能体角色名（如 showrunner / scene_writer）"),
) -> None:
    """查看某智能体的详情（含 system_prompt 摘要）。"""
    orch = _build_orch()
    # 支持 name（中文）或 role（英文 key）
    agent = orch.agents.get(name) or orch.agents.get(name.lower())
    if agent is None:
        # 模糊匹配
        for k, a in orch.agents.items():
            if name.lower() in k.lower() or name in (a.name or ""):
                agent = a
                break
    if agent is None:
        console.print(f"[red]❌ 找不到智能体 {name}[/red]")
        console.print(f"  可用: {', '.join(orch.agents.keys())}")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{agent.name}[/bold cyan] [dim]({agent.role})[/dim]")
    console.print(f"  [bold]描述[/bold]: {agent.description}")
    console.print(f"  [bold]模型[/bold]: {agent.model}")
    console.print(f"  [bold]温度[/bold]: {agent.temperature}")
    console.print(f"  [bold]max_tokens[/bold]: {agent.max_tokens}")
    # system_prompt 可能是 property 或属性
    sp = getattr(agent, "system_prompt", None)
    if callable(sp):
        try:
            sp = sp()
        except Exception:
            sp = None
    if sp:
        preview = sp[:800] + ("..." if len(sp) > 800 else "")
        console.print(f"\n[bold]system_prompt[/bold] (前 800 字):\n{preview}")
    console.print()
