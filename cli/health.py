"""``ss health`` - 系统诊断。

检查 LLM 连接、配置完整性、知识库目录结构。
CI 友好：有问题时 exit code 1。
"""
from __future__ import annotations

import sys

import typer
from rich.panel import Panel

from cli._common import console, load_cfg

app = typer.Typer(
    name="health",
    help="系统诊断（LLM 连接 / 配置校验 / 知识库检查）",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def health() -> None:
    """全面诊断：LLM 连接 + 配置校验 + 知识库目录。"""

    results: list[tuple[str, bool, str]] = []

    # 1. 配置加载
    try:
        cfg = load_cfg()
        results.append(("配置加载", True, f"backend={cfg.backend}, model={cfg.main_model}"))
    except Exception as e:
        results.append(("配置加载", False, str(e)))
        _print_results(results)
        raise typer.Exit(1)

    # 2. 必填字段校验
    missing = []
    if not cfg.llm_base_url:
        missing.append("llm_base_url")
    if not cfg.llm_api_key:
        missing.append("llm_api_key")
    if not cfg.main_model:
        missing.append("main_model")
    if missing:
        results.append(("配置完整性", False, f"缺失字段: {', '.join(missing)}"))
    else:
        results.append(("配置完整性", True, "必填字段齐全"))

    # 3. LLM 连接检查
    if cfg.backend == "llm":
        try:
            import asyncio
            from agents.llm_client import LLMClient
            client = LLMClient(
                base_url=cfg.llm_base_url, api_key=cfg.llm_api_key,
                default_model=cfg.main_model,
            )
            ok = asyncio.run(client.check_health())
            asyncio.run(client.aclose())
            if ok:
                results.append(("LLM 连接", True, f"{cfg.llm_base_url} (model={cfg.main_model})"))
            else:
                results.append(("LLM 连接", False, f"check_health 返回 False"))
        except Exception as e:
            results.append(("LLM 连接", False, str(e)[:200]))
    elif cfg.backend == "ollama":
        try:
            import asyncio
            from agents.ollama_client import OllamaClient
            client = OllamaClient(host=cfg.ollama_host)
            ok = asyncio.run(client.check_health())
            if ok:
                results.append(("Ollama 连接", True, f"{cfg.ollama_host}"))
            else:
                results.append(("Ollama 连接", False, "check_health 返回 False"))
        except Exception as e:
            results.append(("Ollama 连接", False, str(e)[:200]))
    else:
        results.append(("LLM 后端", False, f"未知 backend: {cfg.backend}"))

    # 4. 知识库目录检查
    from pathlib import Path
    kd = Path(cfg.knowledge_dir)
    required_subdirs = ["world", "characters", "story/chapters", "research"]
    missing_dirs = []
    for sub in required_subdirs:
        if not (kd / sub).exists():
            missing_dirs.append(sub)
    if missing_dirs:
        results.append(("知识库目录", False, f"缺失: {', '.join(missing_dirs)}（将自动创建）"))
        # 尝试创建
        try:
            for sub in required_subdirs:
                (kd / sub).mkdir(parents=True, exist_ok=True)
            results.append(("知识库目录", True, f"已自动创建缺失目录于 {kd}"))
        except Exception as e:
            results.append(("知识库目录", False, f"创建失败: {e}"))
    else:
        results.append(("知识库目录", True, f"{kd} 结构完整"))

    # 5. Web 搜索配置（可选）
    if cfg.research_enabled:
        if cfg.web_search_provider in ("doubao", "bocha") and not cfg.web_search_api_key:
            results.append(("Web 搜索", False, f"provider={cfg.web_search_provider} 但未配置 api_key"))
        else:
            results.append(("Web 搜索", True, f"provider={cfg.web_search_provider}"))
    else:
        results.append(("Web 搜索", True, "已禁用（research_enabled=False）"))

    all_ok = _print_results(results)
    if not all_ok:
        raise typer.Exit(1)


def _print_results(results: list[tuple[str, bool, str]]) -> bool:
    """渲染诊断结果，返回是否全部通过。"""
    all_ok = True
    lines = []
    for name, ok, detail in results:
        icon = "✅" if ok else "❌"
        style = "green" if ok else "red"
        lines.append(f"[{style}]{icon} {name}[/{style}]: {detail}")
        if not ok:
            all_ok = False

    console.print(Panel("\n".join(lines), title="🏥 系统诊断", border_style="cyan"))
    if all_ok:
        console.print("[green]所有检查通过 ✅[/green]")
    else:
        console.print("[red]部分检查未通过 ❌[/red]")
    return all_ok


@app.command("models")
def health_models() -> None:
    """列出 LLM 后端可用模型。"""
    import asyncio
    from cli._common import console

    cfg = load_cfg()
    try:
        if cfg.backend == "llm":
            from agents.llm_client import LLMClient
            client = LLMClient(
                base_url=cfg.llm_base_url, api_key=cfg.llm_api_key,
                default_model=cfg.main_model,
            )
        elif cfg.backend == "ollama":
            from agents.ollama_client import OllamaClient
            client = OllamaClient(host=cfg.ollama_host)
        else:
            console.print(f"[red]❌ 未知 backend: {cfg.backend}[/red]")
            raise typer.Exit(1)

        models = asyncio.run(client.list_models())
        if hasattr(client, "aclose"):
            asyncio.run(client.aclose())

        if not models:
            console.print("[dim]后端无可用模型[/dim]")
            return

        from rich.table import Table
        table = Table(title=f"📡 可用模型（{len(models)} 个）")
        table.add_column("模型 ID", style="cyan")
        for m in models:
            model_id = m.get("id", m) if isinstance(m, dict) else str(m)
            table.add_row(model_id)
        console.print(table)
    except Exception as e:
        console.print(f"[red]❌ 获取模型列表失败: {e}[/red]")
        raise typer.Exit(1)
