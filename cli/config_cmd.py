"""``ss config`` - 查看与编辑配置。

模块名 config_cmd 避免与顶层 config/ 包冲突。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.panel import Panel

from cli._common import console, mask_secret, print_json

app = typer.Typer(
    name="config",
    help="查看与编辑配置",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _config_path() -> Path:
    """定位 settings.yaml 路径（尊重 --config 全局选项）。"""
    from cli.main import cli_state
    if cli_state.get("config_path"):
        return Path(cli_state["config_path"])
    return Path("config") / "settings.yaml"


def _load_raw() -> dict:
    p = _config_path()
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _save_raw(data: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")


# 敏感字段：show 时脱敏
_SENSITIVE = {"llm_api_key", "web_search_api_key", "api_key"}


@app.command("show")
def config_show() -> None:
    """脱敏打印当前 settings.yaml。"""
    data = _load_raw()
    if not data:
        console.print(f"[yellow]无配置文件: {_config_path()}[/yellow]")
        console.print("可用模板: config/settings.example.yaml")
        return

    # 脱敏副本
    masked = {}
    for k, v in data.items():
        if k in _SENSITIVE and isinstance(v, str) and v:
            masked[k] = mask_secret(v)
        elif k == "agent_models" and isinstance(v, dict):
            masked[k] = v  # 模型路由不含密钥
        else:
            masked[k] = v

    body = yaml.dump(masked, allow_unicode=True, default_flow_style=False, sort_keys=False)
    console.print(Panel(body, title=f"⚙️ {_config_path()}", border_style="cyan"))


@app.command("path")
def config_path_cmd() -> None:
    """打印当前配置文件路径。"""
    console.print(str(_config_path()))


@app.command("get")
def config_get(
    key: str = typer.Argument(..., help="配置键（如 llm_api_key / main_model / batch_size）"),
) -> None:
    """读取单个配置值。"""
    data = _load_raw()
    # 支持点分路径（agent_models.scene_writer）
    parts = key.split(".")
    val = data
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            console.print(f"[dim]键 {key} 不存在[/dim]")
            raise typer.Exit(1)
    # 敏感值脱敏
    if parts[-1] in _SENSITIVE and isinstance(val, str) and val:
        val = mask_secret(val)
    console.print(val)


@app.command("set")
def config_set(
    key: str = typer.Argument(..., help="配置键（如 main_model / batch_size）"),
    value: str = typer.Argument(..., help="新值（字符串，数字/布尔自动推断）"),
) -> None:
    """写入配置值到 settings.yaml。

    自动类型推断：true/false -> bool，纯数字 -> int，其余为 str。
    不允许通过 CLI 设置敏感字段（llm_api_key 等），请手动编辑文件。
    """
    if key in _SENSITIVE:
        console.print(f"[red]❌ 拒绝通过 CLI 设置敏感字段 {key}，请手动编辑 {_config_path()}[/red]")
        raise typer.Exit(1)

    data = _load_raw()
    # 类型推断
    if value.lower() in ("true", "false"):
        new_val: object = value.lower() == "true"
    elif value.lstrip("-").isdigit():
        new_val = int(value)
    else:
        try:
            new_val = float(value)
        except ValueError:
            new_val = value

    # 支持点分路径
    parts = key.split(".")
    cur = data
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = new_val

    _save_raw(data)
    console.print(f"[green]✅ {key} = {new_val!r}[/green] -> {_config_path()}")
