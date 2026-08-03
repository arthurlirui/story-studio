"""Story Studio CLI - Typer 统一命令行接口。

入口：``ss``（pyproject.toml [project.scripts] 注册）。
保留 ``python main.py`` 作为向后兼容入口（委托到 ``cli.main:app``）。
"""
from cli.main import app

__all__ = ["app"]
