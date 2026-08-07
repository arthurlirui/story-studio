"""``ss status`` - 系统/项目状态。"""
from __future__ import annotations

import typer

from cli._common import console, print_json, print_status_panel

app = typer.Typer(
    name="status",
    help="系统/项目状态",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def status(
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """显示当前项目状态（phase / 章节 / 知识库 / cost 摘要）。

    读取 config.settings.yaml 指向的 knowledge_dir 的 orchestrator 状态。
    """
    from cli._common import build_orch

    _, orch, _ = build_orch()
    status_dict = orch.get_status()

    if fmt == "json":
        print_json(status_dict)
    else:
        print_status_panel(status_dict)
