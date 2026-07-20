"""
Story Studio Configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _expand_env(value: str) -> str:
    """Expand ${VAR} / $VAR references in a config string."""
    return os.path.expandvars(value) if isinstance(value, str) else value


@dataclass
class AgentConfig:
    name: str
    role: str
    description: str
    model: str = "qwen3.6-35b:latest"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt_path: str = ""


@dataclass
class StudioConfig:
    # Backend selection
    backend: str = "llm"  # "llm" or "ollama"
    # LLM API (PCL OpenAI-compatible)
    llm_base_url: str = "https://llmapi.pcl.ac.cn/v1"
    llm_api_key: str = ""
    main_model: str = "DeepSeek-V4-Pro"
    light_model: str = "DeepSeek-V4-Pro"
    # Ollama
    ollama_host: str = "http://localhost:11434"
    # Paths
    knowledge_dir: str = ""
    series_knowledge_dir: str = ""  # Series-level shared knowledge (read-only)
    output_dir: str = ""
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    # Per-agent 模型路由：{agent_role: model_name}，缺键回退 role 默认值。
    # role 默认：scene_writer/showrunner/world_architect/character_designer → main_model；
    #           editor/continuity_keeper/title_designer/hooker/climax_designer/literary_advisor → light_model。
    agent_models: dict[str, str] = field(default_factory=dict)
    max_rounds: int = 3  # 每章自动修订上限（REVISE/REJECT 回灌重写的最大轮数）
    scene_writers: int = 3  # 并行写作的编剧数量
    max_context_chars: int = 60000  # build_context 总字符预算，超出按章节号倒序裁剪最旧摘要


def _load_dotenv(start: Path) -> None:
    """Best-effort .env loader (no external deps). Walks up from start dir."""
    for base in [start, *start.parents]:
        env_file = base / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)
            break


def load_config(config_dir: str | Path = "") -> StudioConfig:
    config_dir = Path(config_dir) if config_dir else Path(__file__).parent
    _load_dotenv(config_dir)
    config_file = config_dir / "settings.yaml"

    cfg = StudioConfig(
        knowledge_dir=str(config_dir.parent / "knowledge"),
        output_dir=str(config_dir.parent / "output"),
    )

    if config_file.exists():
        with open(config_file) as f:
            data = yaml.safe_load(f) or {}

        cfg.backend = data.get("backend", cfg.backend)
        cfg.llm_base_url = data.get("llm_base_url", cfg.llm_base_url)
        cfg.llm_api_key = data.get("llm_api_key", cfg.llm_api_key)
<<<<<<< HEAD
=======
        cfg.volcengine_base_url = data.get("volcengine_base_url", cfg.volcengine_base_url)
        cfg.volcengine_api_key = _expand_env(data.get("volcengine_api_key", cfg.volcengine_api_key))
>>>>>>> 526e7f056fba7e56e975e5f2b965e16e7e911b5c
        cfg.main_model = data.get("main_model", cfg.main_model)
        cfg.light_model = data.get("light_model", cfg.light_model)
        cfg.ollama_host = data.get("ollama_host", cfg.ollama_host)
        cfg.max_rounds = data.get("max_rounds", cfg.max_rounds)
        cfg.scene_writers = data.get("scene_writers", cfg.scene_writers)
        cfg.agent_models = data.get("agent_models", cfg.agent_models) or {}
        cfg.max_context_chars = data.get("max_context_chars", cfg.max_context_chars)

        if "knowledge_dir" in data:
            cfg.knowledge_dir = data["knowledge_dir"]
        if "series_knowledge_dir" in data:
            cfg.series_knowledge_dir = data["series_knowledge_dir"]
        if "output_dir" in data:
            cfg.output_dir = data["output_dir"]

<<<<<<< HEAD
    # Env fallback：settings.yaml 缺密钥时从 LLM_API_KEY 环境变量取
    # （settings.yaml 已加入 .gitignore，不进版本库；生产用 env 注入更安全）
    if not cfg.llm_api_key:
        cfg.llm_api_key = os.environ.get("LLM_API_KEY", "")
=======
    # Environment variable overrides file value (keeps secrets out of the repo).
    cfg.volcengine_api_key = os.environ.get("VOLCENGINE_API_KEY", cfg.volcengine_api_key)
>>>>>>> 526e7f056fba7e56e975e5f2b965e16e7e911b5c

    # Ensure directories exist
    Path(cfg.knowledge_dir).mkdir(parents=True, exist_ok=True)
    for sub in ("world", "characters", "story/chapters", "story/revisions",
                "story/summaries", "story/reviews"):
        Path(cfg.knowledge_dir, sub).mkdir(parents=True, exist_ok=True)
    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)

    return cfg
