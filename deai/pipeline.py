"""去AI化生产环节共享逻辑。

deai stage（pipeline_core.run_deai / run_all.run_deai）的逐章清洗流程在此统一，
避免两处重复。调用方负责实例化 DeaiEngine（从 cfg.deai 读参数）并传入 polish_prompt。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .engine import DeaiEngine

logger = logging.getLogger(__name__)


def make_engine_from_cfg(cfg, llm_client) -> DeaiEngine | None:
    """按 cfg.deai 构造 DeaiEngine；enabled=False 返回 None。"""
    deai_cfg = getattr(cfg, "deai", None)
    if not deai_cfg or not deai_cfg.enabled:
        return None
    band = (deai_cfg.length_min_ratio, deai_cfg.length_max_ratio)
    return DeaiEngine(
        llm_client=llm_client,
        aggressiveness=deai_cfg.aggressiveness,
        length_band=band,
        prompt_version=deai_cfg.prompt_version,
        audit_threshold=deai_cfg.audit_threshold,
    )


async def deai_pass(
    engine: DeaiEngine | None,
    original: str,
    seed: int | None = None,
) -> tuple[str, str]:
    """单章去AI化规则清洗（engine.process）。

    engine 为 None（disabled）时原样返回，附带空报告。
    返回 (processed_text, audit_summary)。
    """
    if not engine or not original or len(original) < 100:
        return original, ""
    processed, report = await engine.process(original, seed=seed)
    return processed, report.summary
