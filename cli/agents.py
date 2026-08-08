"""``ss agents`` - 智能体团队信息。

只读命令：直接从配置读取 agent 元数据，不构造整个 orchestrator，
避免 LLMClient 连接池泄漏和全量构造开销。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from cli._common import console, print_agent_tree, load_cfg

app = typer.Typer(
    name="agents",
    help="智能体团队信息",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _load_agent_configs() -> list[dict]:
    """从配置加载 agent 元数据列表（不构造 orchestrator / LLMClient）。

    orchestrator.__init__ 中的 agent 实例化逻辑是确定性的（角色名、模型路由、
    温度等），这里镜像其结构生成只读的 agent 信息字典。
    """
    cfg = load_cfg(create_dirs=False)

    def model_for(role: str, tier: str = "main") -> str:
        override = cfg.agent_models.get(role)
        if override:
            return override
        return cfg.light_model if tier == "light" else cfg.main_model

    # 与 orchestrator.py __init__ 中的实例化保持一致
    agents = [
        {"name": "总策划", "role": "Showrunner", "description": "主持创作流程, 分配任务, 评审产出",
         "model": model_for("showrunner", "main"), "temperature": 0.6},
        {"name": "世界观架构师", "role": "World Architect", "description": "构建世界观设定",
         "model": model_for("world_architect", "main"), "temperature": 0.8},
        {"name": "角色设计师", "role": "Character Designer", "description": "创建角色档案",
         "model": model_for("character_designer", "main"), "temperature": 0.8},
        {"name": "人物心理学家", "role": "Character Psychologist", "description": "深度心理建模+外貌习惯+语言指纹",
         "model": model_for("character_psychologist", "main"), "temperature": 0.7},
    ]
    # Scene Writers (可变数量)
    writer_count = max(1, cfg.scene_writers)
    for i in range(writer_count):
        agents.append({
            "name": f"场景编剧{i + 1}", "role": "Scene Writer", "description": f"核心写作 #{i + 1}",
            "model": model_for("scene_writer", "main"), "temperature": 0.9,
        })
    agents.extend([
        {"name": "编辑", "role": "Editor", "description": "文字润色",
         "model": model_for("editor", "light"), "temperature": 0.5},
        {"name": "文学顾问", "role": "Literary Advisor", "description": "文学技巧建议",
         "model": model_for("literary_advisor", "light"), "temperature": 0.7},
        {"name": "连续性检查员", "role": "Continuity Keeper", "description": "一致性检查",
         "model": model_for("continuity_keeper", "light"), "temperature": 0.4},
        {"name": "标题设计师", "role": "Title Designer", "description": "设计书名/章节标题",
         "model": model_for("title_designer", "light"), "temperature": 0.8},
        {"name": "钩子设计师", "role": "Hooker", "description": "设计章节钩子",
         "model": model_for("hooker", "light"), "temperature": 0.8},
        {"name": "爽点设计师", "role": "Climax Designer", "description": "设计爽点与高潮",
         "model": model_for("climax_designer", "light"), "temperature": 0.8},
        {"name": "热点研究员", "role": "Topic Researcher", "description": "调研热点/重要事件/同类小说/创作手法",
         "model": model_for("topic_researcher", "light"), "temperature": 0.5},
        {"name": "创新亮点策划师", "role": "Innovator", "description": "基于私有 KB 产出创新亮点清单",
         "model": model_for("innovator", "main"), "temperature": 0.9},
    ])
    return agents


def _find_agent(name: str, agents: list[dict]) -> dict | None:
    """按 name（中文）或 role（英文 key）查找 agent，支持模糊匹配。"""
    for a in agents:
        if name.lower() == a["role"].lower() or name == a["name"]:
            return a
    # 模糊匹配
    for a in agents:
        if name.lower() in a["role"].lower() or name in a["name"]:
            return a
    return None


def _load_system_prompt(role: str) -> str:
    """尝试从 prompts/ 目录加载 system_prompt（只读，不构造 agent）。"""
    # agent 的 system_prompt 通常在 agents/<role>.py 的 property 中硬编码，
    # 这里无法在不实例化的情况下获取完整 prompt。
    # 返回提示信息，而非泄露完整 prompt。
    return f"(请用 ss agents inspect --full 查看完整 prompt，或查看 agents/{role.lower().replace(' ', '_')}.py)"


@app.command("list")
def agents_list() -> None:
    """列出所有智能体（按 main/light tier 分组的树形图）。"""
    agents = _load_agent_configs()
    print_agent_tree(agents)


@app.command("inspect")
def agents_inspect(
    name: str = typer.Argument(..., help="智能体角色名（如 showrunner / scene_writer）"),
) -> None:
    """查看某智能体的详情。"""
    agents = _load_agent_configs()
    agent = _find_agent(name, agents)
    if agent is None:
        console.print(f"[red]❌ 找不到智能体 {name}[/red]")
        console.print(f"  可用: {', '.join(a['role'] for a in agents)}")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{agent['name']}[/bold cyan] [dim]({agent['role']})[/dim]")
    console.print(f"  [bold]描述[/bold]: {agent['description']}")
    console.print(f"  [bold]模型[/bold]: {agent['model']}")
    console.print(f"  [bold]温度[/bold]: {agent['temperature']}")
    console.print(f"  [bold]system_prompt[/bold]: { _load_system_prompt(agent['role'])}")
    console.print()
