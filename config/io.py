"""settings.yaml 读写共享逻辑。

CLI（``ss config``）与 API（``GET/PUT /config``）共用这些函数，
避免脱敏/类型推断/白名单校验逻辑重复，保证两条写入路径行为一致。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# 敏感字段：GET 时脱敏、PUT 时拒绝修改（需手动编辑 settings.yaml）。
SENSITIVE: set[str] = {"llm_api_key", "web_search_api_key", "api_key"}

# 只读字段：GET 时原样返回、PUT 时拒绝（改路径风险高，引导手改 yaml）。
READONLY: set[str] = {
    "knowledge_dir",
    "output_dir",
    "series_knowledge_dir",
    "series_research_dir",
}

# 可通过 PUT /config 写入的顶层标量字段白名单。
# 排除 SENSITIVE / READONLY / agents（load_config 未实际使用 agents 字段）。
_WRITABLE_SCALARS: set[str] = {
    "backend", "llm_base_url", "main_model", "light_model", "ollama_host",
    "max_rounds", "scene_writers", "max_context_chars", "batch_size",
    "merge_gate_rounds", "rate_limit_delay",
    "web_search_provider", "web_search_endpoint",
    "research_enabled", "research_max_topics", "trending_enabled",
}

# 允许写入的顶层键（标量 + 特殊 dict/嵌套结构）。
ALLOWED_KEYS: set[str] = _WRITABLE_SCALARS | {"agent_models", "multi_polish", "deai"}


def default_config_path() -> Path:
    """默认 settings.yaml 路径（config 包目录下的 settings.yaml）。"""
    return Path(__file__).parent / "settings.yaml"


def load_raw(config_path: Path | str | None = None) -> dict:
    """读取 settings.yaml 原始 dict。文件不存在返回空 dict。"""
    p = Path(config_path) if config_path else default_config_path()
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def save_raw(config_path: Path | str | None, data: dict) -> None:
    """写入 settings.yaml（allow_unicode, 保持键顺序）。"""
    p = Path(config_path) if config_path else default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def mask_secret(value: str, visible: int = 4) -> str:
    """密钥脱敏：保留前 visible 位，其余用 * 替代。"""
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "*" * (len(value) - visible)


def mask_config(data: dict) -> dict:
    """返回脱敏副本：SENSITIVE 字段 mask，其余原样。"""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k in SENSITIVE and isinstance(v, str) and v:
            out[k] = mask_secret(v)
        else:
            out[k] = v
    return out


def coerce_value(value: Any) -> Any:
    """字符串值的类型推断（与 CLI config set 一致）。

    字符串 "true"/"false" -> bool，纯数字 -> int，浮点 -> float，其余原样。
    非 str 输入原样返回（API 可能直接传 bool/number）。
    """
    if not isinstance(value, str):
        return value
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.lstrip("-").isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


def apply_update(data: dict, patch: dict) -> tuple[list[str], dict[str, str]]:
    """将 patch 合并到 data（原地修改），返回 (已更新键, 被拒键→原因)。

    - 白名单外的键 → 拒绝
    - SENSITIVE / READONLY 键 → 拒绝
    - multi_polish / agent_models → 递归合并（允许子键写入）
    - 其余白名单标量 → 类型推断后写入
    """
    updated: list[str] = []
    rejected: dict[str, str] = {}

    for key, value in patch.items():
        if key not in ALLOWED_KEYS:
            rejected[key] = "未知字段，不在可写白名单内"
            continue
        if key in SENSITIVE:
            rejected[key] = "敏感字段，请手动编辑 settings.yaml"
            continue
        if key in READONLY:
            rejected[key] = "只读字段，请手动编辑 settings.yaml"
            continue

        if key == "multi_polish" and isinstance(value, dict):
            existing = data.get("multi_polish", {})
            if not isinstance(existing, dict):
                existing = {}
            # models 列表整体替换（前端传完整列表）；enabled/max_concurrent 单字段更新
            for mk, mv in value.items():
                existing[mk] = mv
            data["multi_polish"] = existing
            updated.append("multi_polish")
            continue

        if key == "deai" and isinstance(value, dict):
            existing = data.get("deai", {})
            if not isinstance(existing, dict):
                existing = {}
            # 单字段更新（enabled/aggressiveness/length_*/polish_max_attempts/prompt_version/audit_threshold）
            for dk, dv in value.items():
                existing[dk] = coerce_value(dv) if not isinstance(dv, dict) else dv
            data["deai"] = existing
            updated.append("deai")
            continue

        if key == "agent_models" and isinstance(value, dict):
            existing = data.get("agent_models", {})
            if not isinstance(existing, dict):
                existing = {}
            # 整体替换：前端传全量路由表（空字符串表示清除该角色路由）
            data["agent_models"] = {k: v for k, v in value.items() if v}
            updated.append("agent_models")
            continue

        data[key] = coerce_value(value)
        updated.append(key)

    return updated, rejected
