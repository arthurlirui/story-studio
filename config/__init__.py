"""
Story Studio Configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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
    ollama_host: str = "http://localhost:11434"
    main_model: str = "qwen3.6-35b:latest"
    light_model: str = "qwen2.5:7b"
    knowledge_dir: str = ""
    output_dir: str = ""
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    max_rounds: int = 20


def load_config(config_dir: str | Path = "") -> StudioConfig:
    config_dir = Path(config_dir) if config_dir else Path(__file__).parent / "config"
    config_file = config_dir / "settings.yaml"

    cfg = StudioConfig(
        knowledge_dir=str(config_dir.parent / "knowledge"),
        output_dir=str(config_dir.parent / "output"),
    )

    if config_file.exists():
        with open(config_file) as f:
            data = yaml.safe_load(f) or {}

        cfg.ollama_host = data.get("ollama_host", cfg.ollama_host)
        cfg.main_model = data.get("main_model", cfg.main_model)
        cfg.light_model = data.get("light_model", cfg.light_model)
        cfg.max_rounds = data.get("max_rounds", cfg.max_rounds)

        if "knowledge_dir" in data:
            cfg.knowledge_dir = data["knowledge_dir"]
        if "output_dir" in data:
            cfg.output_dir = data["output_dir"]

    # Ensure directories exist
    Path(cfg.knowledge_dir).mkdir(parents=True, exist_ok=True)
    for sub in ("world", "characters", "story/chapters", "story/revisions"):
        Path(cfg.knowledge_dir, sub).mkdir(parents=True, exist_ok=True)
    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)

    return cfg
