"""``ss repl`` - 交互式 REPL（迁移自 main.py）。

保留原 main.py 的 25 个 slash 命令交互逻辑（/new /next /write /plan ...），
通过委托到 main.main_interactive 实现，避免逻辑重复。

向后兼容：``python main.py``（无参数）也进入此 REPL。
"""
from __future__ import annotations

import asyncio

import typer

from cli._common import console

app = typer.Typer(
    name="repl",
    help="交互式 REPL（/new /next /write 等 slash 命令）",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def repl() -> None:
    """启动交互式 REPL。

    可用命令包括：
    /new <需求> /next /write [章号] /batch /review /revise
    /plan /tasks /run-task /run-all /resume /discard
    /chat <agent> /agents /debate /knowledge /world /chars /outline
    /status /jobs /worklog /phase /research /exit
    """
    # 委托到现有 main.py 的交互逻辑（845 行已验证的 REPL）
    # main.py 的 main_interactive + _dispatch_command 已封装好全部 slash 命令。
    console.print("[dim]启动交互式 REPL（委托 main.py）...[/dim]")

    async def _go():
        # 复用 main.py 的初始化 + 交互循环
        import main as _main
        from cli._common import load_cfg
        from agents.llm_client import init_client
        from orchestrator import StoryOrchestrator

        cfg = load_cfg()
        vc = init_client(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)
        orch = StoryOrchestrator(cfg, client=vc)

        healthy = await vc.check_health()
        if healthy:
            console.print("[green]✅ LLM API 已连接[/green]")
        else:
            console.print("[yellow]⚠️ LLM API 连接异常，但将继续运行...[/yellow]")

        # 断电恢复检测
        try:
            resumable = _main._detect_resumable_run(orch)
            if resumable:
                _main._print_resume_hint(resumable)
        except Exception as e:
            console.print(f"[dim]恢复检测失败: {e}[/dim]")

        await _main.main_interactive(orch)

    asyncio.run(_go())
