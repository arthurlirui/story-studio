"""配置读写端点：``GET/PUT /config``。

与 CLI ``ss config`` 共享 ``config.io`` 逻辑，脱敏与白名单策略一致。
写回 settings.yaml 后重载 JobRunner 内存配置，使新任务立即生效。
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from config.io import SENSITIVE, READONLY, apply_update, load_raw, mask_config, save_raw

router = APIRouter()


def _config_path() -> Path:
    """定位 settings.yaml 路径。优先 STORY_STUDIO_CONFIG 环境变量，否则默认 config 包目录。"""
    env_path = os.environ.get("STORY_STUDIO_CONFIG")
    if env_path:
        p = Path(env_path)
        return p if p.suffix in (".yaml", ".yml") else p / "settings.yaml"
    return Path("config") / "settings.yaml"


@router.get("/config")
async def get_config() -> dict:
    """返回脱敏后的全量配置。敏感字段 mask，只读字段原样返回。"""
    data = load_raw(_config_path())
    return mask_config(data)


@router.put("/config")
async def put_config(patch: dict = Body(...)) -> dict:
    """部分更新 settings.yaml。

    仅接受白名单内字段；SENSITIVE/READONLY 字段拒绝写入。
    写回后重载 JobRunner 内存配置，使新任务立即用新参数。
    """
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")

    path = _config_path()
    data = load_raw(path)
    updated, rejected = apply_update(data, patch)

    if updated:
        save_raw(path, data)
        # 重载内存配置，使新任务立即生效（运行中任务不受影响）
        try:
            from api import get_runner
            from config import load_config
            runner = get_runner()
            runner.cfg = load_config(create_dirs=False)
        except Exception:
            # 配置重载失败不影响已写入的 yaml；下次启动仍会加载新配置
            pass

    return {"updated": updated, "rejected": rejected}


@router.get("/config/paths")
async def get_config_paths() -> dict:
    """返回当前配置文件路径与 jobs 目录（只读信息）。"""
    return {
        "config_file": str(_config_path()),
        "jobs_dir": os.environ.get("STORY_STUDIO_JOBS_DIR", "jobs"),
    }


# 重新导出供外部模块使用
__all__ = ["router", "SENSITIVE", "READONLY"]
