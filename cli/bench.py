"""``ss bench`` - LLM 性能基准测试。

薄封装 ``tools/bench_llm_perf.py`` 的核心逻辑。
测试维度：TTFT、流式吞吐、轻任务延迟、章节写作、3路并发。
"""
from __future__ import annotations

import asyncio
from typing import Optional

import typer

from cli._common import console, load_cfg

app = typer.Typer(
    name="bench",
    help="LLM 性能基准测试",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def bench(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="指定模型（默认用 main_model）"),
    rounds: int = typer.Option(1, "--rounds", "-r", min=1, max=10, help="重复轮次（取平均值）"),
    list_models: bool = typer.Option(False, "--list", "-l", help="列出 settings.yaml 中配置的模型后退出"),
) -> None:
    """LLM 模型性能基准 — 面向 story-studio 真实工作负载。

    测试维度：TTFT、流式吞吐、轻任务延迟、章节写作、3路并发。
    """

    cfg = load_cfg()

    # 收集要测试的模型
    if list_models:
        models = set()
        if cfg.main_model:
            models.add(cfg.main_model)
        if cfg.light_model:
            models.add(cfg.light_model)
        for m in (cfg.agent_models or {}).values():
            if isinstance(m, str):
                models.add(m)
        if models:
            console.print("[bold]配置中的模型:[/bold]")
            for m in sorted(models):
                console.print(f"  • {m}")
        else:
            console.print("[dim]未配置任何模型[/dim]")
        return

    models_to_test = [model] if model else [cfg.main_model]
    if not models_to_test or not models_to_test[0]:
        console.print("[red]❌ 未指定模型，且 settings.yaml 未配置 main_model[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]🔬 LLM 性能基准[/cyan]")
    console.print(f"  endpoint: {cfg.llm_base_url}")
    console.print(f"  models: {', '.join(models_to_test)}")
    console.print(f"  rounds: {rounds}\n")

    async def _go():
        from tools.bench_llm_perf import run_for_model, _fmt

        all_results: list[dict] = []
        for m in models_to_test:
            console.print(f"▶ [bold]{m}[/bold] ...", flush=True)
            round_results = []
            for r in range(rounds):
                if rounds > 1:
                    console.print(f"  [dim]round {r + 1}/{rounds}[/dim]")
                result = await run_for_model(cfg, m)
                round_results.append(result)

            if rounds == 1:
                all_results.append(round_results[0])
                console.print(_fmt(round_results[0]))
            else:
                # 多轮取平均值
                all_results.append(round_results[-1])  # 最后一轮详情
                console.print(_fmt(round_results[-1]))

        # 汇总表
        console.print("\n" + "=" * 70)
        console.print("[bold]汇总[/bold]")
        console.print("=" * 70)
        console.print(f"{'model':<22} {'TTFT':>6} {'tok/s':>7} {'chapter':>8} {'3并行':>10} {'ok':>4}")
        for r in all_results:
            if "fatal" in r:
                console.print(f"{r['model']:<22} [red]FATAL {r['fatal'][:50]}[/red]")
                continue
            t = r["ttft_stream"]
            c = r["chapter"]
            k = r["concurrent3"]
            console.print(
                f"{r['model']:<22} {t['ttft_s']:>5.2f}s {t['stream_tps']:>6.1f} "
                f"{c['total_s']:>7.1f}s {k['wall_s']:>9.1f}s {k['ok']:>3}/3"
            )

    asyncio.run(_go())
