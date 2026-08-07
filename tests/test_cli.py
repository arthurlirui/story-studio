"""CLI 命令注册与参数解析测试。

用 typer.testing.CliRunner 测试 ``ss`` 命令树的命令注册、帮助输出、
参数解析和退出码，不触发实际的 LLM 调用或 orchestrator 初始化。

覆盖：
- 根命令帮助（所有子命令已注册）
- 各子命令组帮助
- --version / 无效命令的行为
- config get/set 的参数解析（不实际写文件）
- show / health / short / bench / jobs tasks 的命令存在性
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


# ── 根命令 ──────────────────────────────────────────────────────


class TestRootApp:
    """根 ``ss`` 命令。"""

    def test_help_lists_all_commands(self):
        """``ss --help`` 应列出所有注册的子命令。"""
        r = runner.invoke(app, ["--help"])
        assert r.exit_code == 0
        # 核心命令
        for cmd in ["submit", "gui", "run", "jobs", "list", "show",
                     "export", "config", "agents", "status",
                     "health", "short", "bench", "repl"]:
            assert cmd in r.output, f"命令 '{cmd}' 未出现在 --help 输出中"

    def test_no_args_shows_help(self):
        """裸 ``ss`` 应显示帮助（no_args_is_help=True）。"""
        r = runner.invoke(app, [])
        assert r.exit_code != 0  # Typer 在 no_args_is_help 时返回非零

    def test_invalid_command_exits_nonzero(self):
        """无效命令应返回非零退出码。"""
        r = runner.invoke(app, ["nonexistent-command"])
        assert r.exit_code != 0


# ── ss run ──────────────────────────────────────────────────────


class TestRunSubapp:
    """``ss run`` 子命令组。"""

    def test_help_lists_all_subcommands(self):
        r = runner.invoke(app, ["run", "--help"])
        assert r.exit_code == 0
        for cmd in ["pipeline", "short", "stage", "polish", "batch", "revise", "style"]:
            assert cmd in r.output, f"'run {cmd}' 未注册"

    def test_pipeline_list_flag(self):
        """``ss run pipeline --list`` 应列出 tasks/ 目录。"""
        r = runner.invoke(app, ["run", "pipeline", "--list"])
        # 即使 tasks/ 目录不存在，也不应崩溃
        assert r.exit_code == 0

    def test_stage_invalid_phase(self):
        """``ss run stage invalid`` 应报错并退出。"""
        r = runner.invoke(app, ["run", "stage", "invalid_phase"])
        assert r.exit_code != 0

    def test_style_list_flag(self):
        """``ss run style --list`` 应列出可用风格。"""
        r = runner.invoke(app, ["run", "style", "--list"])
        assert r.exit_code == 0


# ── ss jobs ─────────────────────────────────────────────────────


class TestJobsSubapp:
    """``ss jobs`` 子命令组。"""

    def test_help_lists_all_subcommands(self):
        r = runner.invoke(app, ["jobs", "--help"])
        assert r.exit_code == 0
        for cmd in ["list", "show", "cancel", "retry", "tasks"]:
            assert cmd in r.output, f"'jobs {cmd}' 未注册"

    def test_jobs_list_no_jobs(self):
        """``ss jobs list`` 在无 Job 时应优雅退出。"""
        r = runner.invoke(app, ["jobs", "list"])
        # 无 Job 时不报错，exit_code 应为 0
        assert r.exit_code == 0

    def test_jobs_show_nonexistent(self):
        """``ss jobs show nonexistent`` 应报错退出。"""
        r = runner.invoke(app, ["jobs", "show", "nonexistent-job-id"])
        assert r.exit_code == 1

    def test_jobs_tasks_help(self):
        """``ss jobs tasks --help`` 应显示任务管理帮助。"""
        r = runner.invoke(app, ["jobs", "tasks", "--help"])
        assert r.exit_code == 0


# ── ss show ─────────────────────────────────────────────────────


class TestShowSubapp:
    """``ss show`` 子命令组。"""

    def test_help_lists_all_subcommands(self):
        r = runner.invoke(app, ["show", "--help"])
        assert r.exit_code == 0
        for cmd in ["outline", "world", "characters", "chapter", "cost", "quality", "research"]:
            assert cmd in r.output, f"'show {cmd}' 未注册"

    def test_show_outline_nonexistent(self):
        """``ss show outline nonexistent`` 应报错退出。"""
        r = runner.invoke(app, ["show", "outline", "nonexistent-novel-id"])
        assert r.exit_code == 1


# ── ss health ───────────────────────────────────────────────────


class TestHealthSubapp:
    """``ss health`` 子命令组。"""

    def test_help(self):
        r = runner.invoke(app, ["health", "--help"])
        assert r.exit_code == 0
        assert "models" in r.output

    def test_health_models_help(self):
        r = runner.invoke(app, ["health", "models", "--help"])
        assert r.exit_code == 0


# ── ss short ────────────────────────────────────────────────────


class TestShortSubapp:
    """``ss short`` 子命令组。"""

    def test_help_lists_all_subcommands(self):
        r = runner.invoke(app, ["short", "--help"])
        assert r.exit_code == 0
        for cmd in ["generate", "trends", "genres"]:
            assert cmd in r.output, f"'short {cmd}' 未注册"

    def test_short_genres(self):
        """``ss short genres`` 应列出 genre 配置。"""
        r = runner.invoke(app, ["short", "genres"])
        assert r.exit_code == 0


# ── ss bench ────────────────────────────────────────────────────


class TestBenchSubapp:
    """``ss bench`` 子命令组。"""

    def test_help(self):
        r = runner.invoke(app, ["bench", "--help"])
        assert r.exit_code == 0
        assert "LLM" in r.output or "基准" in r.output

    def test_bench_list_models(self):
        """``ss bench --list`` 应列出配置的模型。"""
        r = runner.invoke(app, ["bench", "--list"])
        assert r.exit_code == 0


# ── ss list ─────────────────────────────────────────────────────


class TestListSubapp:
    """``ss list`` 子命令组。"""

    def test_help_lists_all_subcommands(self):
        r = runner.invoke(app, ["list", "--help"])
        assert r.exit_code == 0
        for cmd in ["series", "novels", "chapters"]:
            assert cmd in r.output, f"'list {cmd}' 未注册"

    def test_list_series(self):
        """``ss list series`` 应正常执行（即使无 series/ 目录）。"""
        r = runner.invoke(app, ["list", "series"])
        assert r.exit_code == 0


# ── ss config ───────────────────────────────────────────────────


class TestConfigSubapp:
    """``ss config`` 子命令组。"""

    def test_help_lists_all_subcommands(self):
        r = runner.invoke(app, ["config", "--help"])
        assert r.exit_code == 0
        for cmd in ["show", "path", "get", "set"]:
            assert cmd in r.output, f"'config {cmd}' 未注册"

    def test_config_path(self):
        """``ss config path`` 应打印路径。"""
        r = runner.invoke(app, ["config", "path"])
        assert r.exit_code == 0
        assert "settings.yaml" in r.output

    def test_config_set_sensitive_key_rejected(self):
        """``ss config set llm_api_key xxx`` 应被拒绝。"""
        r = runner.invoke(app, ["config", "set", "llm_api_key", "test123"])
        assert r.exit_code == 1
        assert "拒绝" in r.output or "敏感" in r.output


# ── ss agents ───────────────────────────────────────────────────


class TestAgentsSubapp:
    """``ss agents`` 子命令组。"""

    def test_help_lists_all_subcommands(self):
        r = runner.invoke(app, ["agents", "--help"])
        assert r.exit_code == 0
        for cmd in ["list", "inspect"]:
            assert cmd in r.output, f"'agents {cmd}' 未注册"


# ── 全局选项 ────────────────────────────────────────────────────


class TestGlobalOptions:
    """全局选项传递。"""

    def test_verbose_flag_accepted(self):
        """``ss -v --help`` 应正常工作。"""
        r = runner.invoke(app, ["-v", "--help"])
        assert r.exit_code == 0

    def test_no_interaction_flag_accepted(self):
        """``ss -n --help`` 应正常工作。"""
        r = runner.invoke(app, ["-n", "--help"])
        assert r.exit_code == 0
