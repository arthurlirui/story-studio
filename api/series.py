"""系列与短篇类型只读端点。

扫描 series/ 目录和 short_story/skill_configs/，为前端项目列表和类型选择器提供数据。
不调用 LLM、不修改状态。
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/series")
async def list_series():
    """列出所有创作系列（扫 series/ 目录）。"""
    series_dir = Path("series")
    if not series_dir.exists():
        return {"series": []}
    items = []
    for d in sorted(series_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            variants_dir = d / "variants"
            variants = []
            if variants_dir.exists():
                for v in sorted(variants_dir.iterdir()):
                    if v.is_dir() and not v.name.startswith("."):
                        has_outline = (v / "knowledge" / "story" / "outline.md").exists() or \
                                      (v / "outline.md").exists()
                        variants.append({"name": v.name, "has_outline": has_outline})
            items.append({
                "name": d.name,
                "variants": variants,
                "has_bible": (d / "knowledge" / "series_bible.md").exists(),
            })
    return {"series": items}


@router.get("/series/{name}/variants")
async def list_variants(name: str):
    """列出某系列的变体目录。"""
    series_path = Path("series") / name
    if not series_path.exists():
        raise HTTPException(status_code=404, detail=f"series {name} not found")
    variants = []
    variants_dir = series_path / "variants"
    if variants_dir.exists():
        for v in sorted(variants_dir.iterdir()):
            if v.is_dir() and not v.name.startswith("."):
                variants.append({
                    "name": v.name,
                    "path": str(v),
                    "has_outline": (v / "knowledge" / "story" / "outline.md").exists() or
                                   (v / "outline.md").exists(),
                })
    return {"series": name, "variants": variants}


@router.get("/genres")
async def list_genres():
    """列出短篇类型配置（short_story/skill_configs/*.json）。"""
    cfg_dir = Path("short_story") / "skill_configs"
    if not cfg_dir.exists():
        return {"genres": []}
    genres = []
    for f in sorted(cfg_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            genres.append({
                "slug": f.stem,
                "genre": data.get("genre", f.stem),
                "genre_name_zh": data.get("genre_name_zh", data.get("genre", f.stem)),
                "category": data.get("category", ""),
                "default_pov": data.get("default_pov", ""),
                "word_range": data.get("word_range", []),
            })
        except (json.JSONDecodeError, ValueError):
            continue
    return {"genres": genres}
