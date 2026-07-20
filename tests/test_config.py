"""单元测试：config.load_config 的 yaml→dataclass、env fallback、目录创建。

覆盖 Stage 5.5：
- 默认值（无 settings.yaml 时）
- yaml 字段覆盖默认值
- agent_models / max_context_chars 新字段读取
- LLM_API_KEY env fallback（llm_api_key 为空时）
- 目录自动创建（含新的 story/summaries、story/reviews）
- settings.yaml 已从版本库移除（gitignored），load_config 不应依赖它存在
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from config import StudioConfig, load_config


class TestDefaults:
    def test_defaults_without_settings_file(self, tmp_path: Path):
        """无 settings.yaml 时用默认值。"""
        cfg = load_config(config_dir=str(tmp_path))
        assert cfg.backend == "llm"
        assert cfg.main_model == "DeepSeek-V4-Pro"
        assert cfg.max_rounds == 3
        assert cfg.scene_writers == 3
        assert cfg.max_context_chars == 60000
        assert cfg.agent_models == {}

    def test_default_paths_relative_to_config_dir(self, tmp_path: Path):
        cfg = load_config(config_dir=str(tmp_path))
        # 默认 knowledge_dir = config_dir.parent / "knowledge"
        assert cfg.knowledge_dir == str(tmp_path.parent / "knowledge")
        assert cfg.output_dir == str(tmp_path.parent / "output")


class TestYamlOverride:
    def test_yaml_overrides_defaults(self, tmp_path: Path):
        (tmp_path / "settings.yaml").write_text(
            "backend: ollama\n"
            "main_model: custom-main\n"
            "light_model: custom-light\n"
            "max_rounds: 5\n"
            "scene_writers: 7\n"
            "max_context_chars: 30000\n",
            encoding="utf-8",
        )
        cfg = load_config(config_dir=str(tmp_path))
        assert cfg.backend == "ollama"
        assert cfg.main_model == "custom-main"
        assert cfg.light_model == "custom-light"
        assert cfg.max_rounds == 5
        assert cfg.scene_writers == 7
        assert cfg.max_context_chars == 30000

    def test_yaml_agent_models_read(self, tmp_path: Path):
        (tmp_path / "settings.yaml").write_text(
            "agent_models:\n"
            "  editor: editor-model\n"
            "  showrunner: sr-model\n",
            encoding="utf-8",
        )
        cfg = load_config(config_dir=str(tmp_path))
        assert cfg.agent_models == {"editor": "editor-model", "showrunner": "sr-model"}

    def test_yaml_paths_override(self, tmp_path: Path):
        (tmp_path / "settings.yaml").write_text(
            "knowledge_dir: /tmp/k\n"
            "output_dir: /tmp/o\n",
            encoding="utf-8",
        )
        cfg = load_config(config_dir=str(tmp_path))
        assert cfg.knowledge_dir == "/tmp/k"
        assert cfg.output_dir == "/tmp/o"


class TestEnvFallback:
    def test_env_fallback_when_key_empty(self, tmp_path: Path, monkeypatch):
        """settings.yaml 无 llm_api_key 时从 LLM_API_KEY env 取。"""
        (tmp_path / "settings.yaml").write_text("llm_api_key: ''\n", encoding="utf-8")
        monkeypatch.setenv("LLM_API_KEY", "env-key-123")
        cfg = load_config(config_dir=str(tmp_path))
        assert cfg.llm_api_key == "env-key-123"

    def test_env_not_used_when_yaml_has_key(self, tmp_path: Path, monkeypatch):
        """settings.yaml 有 llm_api_key 时 env 不覆盖。"""
        (tmp_path / "settings.yaml").write_text(
            "llm_api_key: yaml-key\n", encoding="utf-8"
        )
        monkeypatch.setenv("LLM_API_KEY", "env-key-123")
        cfg = load_config(config_dir=str(tmp_path))
        assert cfg.llm_api_key == "yaml-key"

    def test_no_key_anywhere_returns_empty(self, tmp_path: Path, monkeypatch):
        """yaml 和 env 都无 key 时返回空串（不报错）。"""
        (tmp_path / "settings.yaml").write_text("llm_api_key: ''\n", encoding="utf-8")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        cfg = load_config(config_dir=str(tmp_path))
        assert cfg.llm_api_key == ""


class TestDirCreation:
    def test_creates_knowledge_subdirs(self, tmp_path: Path):
        """load_config 应自动创建 knowledge 子目录（含 summaries/reviews）。"""
        cfg = load_config(config_dir=str(tmp_path))
        kdir = Path(cfg.knowledge_dir)
        for sub in ("world", "characters", "story/chapters", "story/revisions",
                    "story/summaries", "story/reviews"):
            assert (kdir / sub).exists(), f"缺失子目录: {sub}"

    def test_creates_output_dir(self, tmp_path: Path):
        cfg = load_config(config_dir=str(tmp_path))
        assert Path(cfg.output_dir).exists()
