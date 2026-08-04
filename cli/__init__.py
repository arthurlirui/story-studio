"""Story Studio CLI - Typer 统一命令行接口。

入口：``ss``（pyproject.toml [project.scripts] 注册）。
保留 ``python main.py`` 作为向后兼容入口（委托到 ``cli.main:app``）。

直接 import 会触发 app 构造（拉起所有子命令模块）。为支持 ``python -m cli.main``，
这里不在 __init__ 顶层 import app；请用 ``from cli.main import app``。
"""
# 不在 __init__ 顶层导入 app，避免 runpy 的 RuntimeWarning。

