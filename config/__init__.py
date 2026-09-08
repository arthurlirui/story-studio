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
class MultiPolishModelConfig:
    """单个模型的润色配置。"""
    name: str = ""              # 模型名，如 DeepSeek-V4-Pro
    temperature: float = 0.8    # 采样温度
    max_tokens: int = 12000     # 最大输出 token
    prompt_version: str = "v4"  # 润色提示词版本


@dataclass
class MultiPolishConfig:
    """多模型润色总配置。"""
    enabled: bool = True
    models: list[MultiPolishModelConfig] = field(default_factory=list)
    max_concurrent: int = 3     # 最大并发数


@dataclass
class DeaiConfig:
    """去AI化引擎配置。

    对应 deai/engine.py 的 DeaiEngine 参数 + 终审质量门阈值。
    - aggressiveness: 0.0-1.0，控制规则重写的激进程度（同义词变异/段落碎片化/长句拆分触发概率）
    - length_min/max_ratio: 润色前后字数合规区间（润色后字数 / 原文字数），
      超出区间触发重试或截断。对应短篇 pipeline 的 TARGET/ACCEPT 比例。
    - prompt_version: DeaiEngine LLM 重写提示词版本，对应 deai/prompts/rewrite_{version}.txt
    - audit_threshold: 终审 audit 评分低于此值触发一轮 engine.process() 重写（0-50 分制）
    """
    enabled: bool = True
    aggressiveness: float = 0.4
    length_min_ratio: float = 0.90
    length_max_ratio: float = 1.15
    polish_max_attempts: int = 4
    prompt_version: str = "v1"
    audit_threshold: int = 35


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
    series_research_dir: str = ""  # Series-level shared research KB (read-only)
    output_dir: str = ""
    # 网络搜索 + 私有调研 KB
    web_search_provider: str = "doubao"  # "doubao" | "bocha" | "mock"
    web_search_api_key: str = ""  # 留空从 env WEB_SEARCH_API_KEY 读
    web_search_endpoint: str = ""  # 留空用 provider 默认 endpoint
    research_enabled: bool = True  # 关闭则跳过 research/innovate 任务
    research_max_topics: int = 4  # 检索主题数（热点/重要事件/同类小说/创作手法）
    trending_enabled: bool = True  # 关闭则跳过 trending（热词研究）任务
    # REST API 鉴权：留空则不启用鉴权（仅适合本地/内网）；
    # 设置后所有 /novels* 端点要求请求头 X-API-Key 匹配该值。/health 始终开放。
    api_key: str = ""
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    # Per-agent 模型路由：{agent_role: model_name}，缺键回退 role 默认值。
    # role 默认：scene_writer/showrunner/world_architect/character_designer → main_model；
    #           editor/continuity_keeper/title_designer/hooker/climax_designer/literary_advisor → light_model。
    agent_models: dict[str, str] = field(default_factory=dict)
    # 多模型润色配置
    multi_polish: MultiPolishConfig = field(default_factory=MultiPolishConfig)
    # 去AI化引擎配置
    deai: DeaiConfig = field(default_factory=DeaiConfig)
    max_rounds: int = 3  # 每章自动修订上限（REVISE/REJECT 回灌重写的最大轮数）
    scene_writers: int = 3  # 并行写作的编剧数量
    max_context_chars: int = 60000  # build_context 总字符预算，超出按章节号倒序裁剪最旧摘要
    batch_size: int = 3  # 单批次并行写作的默认章节数（仍受 scene_writers 上限约束）
    merge_gate_rounds: int = 1  # 融合门冲突章定向重写的轮数上限
    rate_limit_delay: float = 0.0  # API 调用间固定延迟（秒）；0 = 禁用，让 LLMClient 的 429 退避做唯一限流


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


def ensure_directories(cfg: StudioConfig) -> None:
    """确保 knowledge_dir / output_dir 及其子目录存在。

    从 load_config 中提取为独立函数，避免只读命令（ss config show / ss agents list）
    触发目录创建副作用。需要写入的入口（StoryOrchestrator / JobRunner / build_orch）
    应显式调用此函数。
    """
    Path(cfg.knowledge_dir).mkdir(parents=True, exist_ok=True)
    for sub in ("world", "characters", "story/chapters", "story/revisions",
                "story/summaries", "story/reviews", "research"):
        Path(cfg.knowledge_dir, sub).mkdir(parents=True, exist_ok=True)
    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)


def load_config(config_dir: str | Path = "", *, create_dirs: bool = True) -> StudioConfig:
    """加载配置。

    Args:
        config_dir: 配置目录路径（含 settings.yaml）。空串则用 config/ 包目录。
        create_dirs: 是否自动创建 knowledge_dir / output_dir 子目录。
            只读命令（ss config show / ss agents list）传 False 避免副作用。
    """
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
        cfg.main_model = data.get("main_model", cfg.main_model)
        cfg.light_model = data.get("light_model", cfg.light_model)
        cfg.ollama_host = data.get("ollama_host", cfg.ollama_host)
        cfg.max_rounds = data.get("max_rounds", cfg.max_rounds)
        cfg.scene_writers = data.get("scene_writers", cfg.scene_writers)
        cfg.agent_models = data.get("agent_models", cfg.agent_models) or {}

        # 多模型润色配置
        mp_data = data.get("multi_polish", {})
        if mp_data:
            mp_models = []
            for m in mp_data.get("models", []):
                mp_models.append(MultiPolishModelConfig(
                    name=m.get("name", ""),
                    temperature=m.get("temperature", 0.8),
                    max_tokens=m.get("max_tokens", 12000),
                    prompt_version=m.get("prompt_version", "v4"),
                ))
            cfg.multi_polish = MultiPolishConfig(
                enabled=mp_data.get("enabled", True),
                models=mp_models,
                max_concurrent=mp_data.get("max_concurrent", 3),
            )

        # 去AI化引擎配置
        deai_data = data.get("deai", {})
        if deai_data:
            cfg.deai = DeaiConfig(
                enabled=deai_data.get("enabled", True),
                aggressiveness=float(deai_data.get("aggressiveness", 0.4)),
                length_min_ratio=float(deai_data.get("length_min_ratio", 0.90)),
                length_max_ratio=float(deai_data.get("length_max_ratio", 1.15)),
                polish_max_attempts=int(deai_data.get("polish_max_attempts", 4)),
                prompt_version=deai_data.get("prompt_version", "v1"),
                audit_threshold=int(deai_data.get("audit_threshold", 35)),
            )

        cfg.max_context_chars = data.get("max_context_chars", cfg.max_context_chars)
        cfg.batch_size = data.get("batch_size", cfg.batch_size)
        cfg.merge_gate_rounds = data.get("merge_gate_rounds", cfg.merge_gate_rounds)
        cfg.web_search_provider = data.get("web_search_provider", cfg.web_search_provider)
        cfg.web_search_api_key = data.get("web_search_api_key", cfg.web_search_api_key)
        cfg.web_search_endpoint = data.get("web_search_endpoint", cfg.web_search_endpoint)
        cfg.research_enabled = data.get("research_enabled", cfg.research_enabled)
        cfg.research_max_topics = data.get("research_max_topics", cfg.research_max_topics)
        cfg.trending_enabled = data.get("trending_enabled", cfg.trending_enabled)
        cfg.api_key = data.get("api_key", cfg.api_key)

        if "knowledge_dir" in data:
            cfg.knowledge_dir = data["knowledge_dir"]
        if "series_knowledge_dir" in data:
            cfg.series_knowledge_dir = data["series_knowledge_dir"]
        if "series_research_dir" in data:
            cfg.series_research_dir = data["series_research_dir"]
        if "output_dir" in data:
            cfg.output_dir = data["output_dir"]

    # Env fallback：settings.yaml 缺密钥时从 LLM_API_KEY 环境变量取
    # （settings.yaml 已加入 .gitignore，不进版本库；生产用 env 注入更安全）
    if not cfg.llm_api_key:
        cfg.llm_api_key = os.environ.get("LLM_API_KEY", "")
    if not cfg.web_search_api_key:
        cfg.web_search_api_key = os.environ.get("WEB_SEARCH_API_KEY", "")
    # API 鉴权密钥 env fallback
    if not cfg.api_key:
        cfg.api_key = os.environ.get("STORY_STUDIO_API_KEY", "")

    # 确保目录存在（可由调用方通过 create_dirs=False 关闭）
    if create_dirs:
        ensure_directories(cfg)

    return cfg
