#!/usr/bin/env python3
"""Create a new long-form novel variant under the 《破镜之后》 series."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

SERIES_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = SERIES_ROOT / "templates"
VARIANTS = SERIES_ROOT / "variants"

MODE_LABELS = {
    "modern": "现言",
    "historical": "古言",
    "fantasy": "幻言",
}

ENDING_LABELS = {
    "reunion": "破镜重圆",
    "no_forgiveness": "绝不原谅",
    "new_love": "新感情胜利",
    "solo_ascension": "孤身登顶",
    "bittersweet_reconciliation": "不复合但和解",
}


def safe_filename(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", s.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "untitled")[:max_len]


def default_logline(title: str, mode: str, ending: str, wound: str, years: float) -> str:
    mode_cn = MODE_LABELS.get(mode, mode)
    ending_cn = ENDING_LABELS.get(ending, ending)
    return f"{mode_cn}长篇。故事从女主被{wound}伤害{years:g}年后切入；旧人重新出现，迟来的真相与悔意逼近，而她必须决定是否{ending_cn}。"


def build_seed(args: argparse.Namespace) -> dict:
    template = json.loads((TEMPLATES / "novel_seed_template.json").read_text(encoding="utf-8"))
    template.update({
        "series": "破镜之后",
        "title": args.title,
        "mode": args.mode,
        "ending": args.ending,
        "years_after": args.years,
        "logline": args.logline or default_logline(args.title, args.mode, args.ending, args.wound, args.years),
        "wound_type": args.wound,
        "misunderstanding": args.misunderstanding,
        "power_structure": args.power_structure,
        "irreversible_loss": args.loss,
        "plot_engine": args.plot_engine,
        "opening_hook": args.hook,
        "cover_direction": args.cover_direction,
    })
    return template


def write_project_files(project_dir: Path, seed: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "chapters").mkdir(exist_ok=True)

    (project_dir / "seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")

    shutil.copy2(TEMPLATES / "volume_outline_template.md", project_dir / "outline.md")
    shutil.copy2(TEMPLATES / "character_sheet_template.md", project_dir / "characters.md")
    shutil.copy2(TEMPLATES / "chapter_template.md", project_dir / "chapter_template.md")

    cover = json.loads((TEMPLATES / "cover_brief_template.json").read_text(encoding="utf-8"))
    cover["title"] = seed["title"]
    cover["subtitle"] = f"{MODE_LABELS.get(seed['mode'], seed['mode'])} · {ENDING_LABELS.get(seed['ending'], seed['ending'])}"
    cover["positive_prompt"] = cover["positive_prompt"].replace("Chinese female romance novel", f"Chinese {MODE_LABELS.get(seed['mode'], seed['mode'])} female romance novel")
    (project_dir / "cover_brief.json").write_text(json.dumps(cover, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# {seed['title']}

- 系列：破镜之后
- 模式：{seed['mode']} / {MODE_LABELS.get(seed['mode'], seed['mode'])}
- 结局路线：{seed['ending']} / {ENDING_LABELS.get(seed['ending'], seed['ending'])}
- 伤害后时间：{seed['years_after']} 年
- 伤害类型：{seed['wound_type']}
- 剧情发动机：{seed['plot_engine']}

## 一句话

{seed['logline']}

## 关联知识库

- ../../knowledge/series_bible.md
- ../../knowledge/world_modes.md
- ../../knowledge/emotional_conflict_library.md
- ../../knowledge/character_archetypes.md
- ../../knowledge/plot_engines.md
- ../../knowledge/style_guide.md
- ../../knowledge/continuity_rules.md

## 推荐流程

1. 根据 seed.json 完成人物卡 characters.md。
2. 根据 outline.md 完成四卷大纲。
3. 生成 chapter_plan.md。
4. 按 chapters/ 输出章节。
5. 用 ../../templates/cover_brief_template.json 或本目录 cover_brief.json 生成封面。
"""
    (project_dir / "README.md").write_text(readme, encoding="utf-8")

    continuity = f"""# 连续性记录：{seed['title']}

## 固定事实

- 故事从伤害 {seed['years_after']} 年后切入。
- 女主已经离开旧关系。
- 结局路线：{seed['ending']}。

## 待补充

- [ ] 女主不可逆损失细节
- [ ] 当年真相三层揭露
- [ ] 旧人赎罪代价
- [ ] 终局选择
"""
    (project_dir / "continuity_log.md").write_text(continuity, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a new 《破镜之后》 long-form novel variant.")
    ap.add_argument("--title", required=True, help="Novel title")
    ap.add_argument("--mode", choices=["modern", "historical", "fantasy"], required=True)
    ap.add_argument("--ending", choices=list(ENDING_LABELS), default="no_forgiveness")
    ap.add_argument("--wound", default="误会背叛", help="Main wound description or W-code")
    ap.add_argument("--years", type=float, default=5)
    ap.add_argument("--misunderstanding", default="M01")
    ap.add_argument("--power-structure", default="P01")
    ap.add_argument("--loss", default="待设计的不可逆损失")
    ap.add_argument("--plot-engine", default="PE01")
    ap.add_argument("--hook", default="旧人以为她还在原地，第一章发现她已拥有新身份。")
    ap.add_argument("--cover-direction", default="破镜、雨夜、女主背影、旧人远景、迟来悔意")
    ap.add_argument("--logline", default="")
    ap.add_argument("--slug", default="", help="Optional directory name")
    args = ap.parse_args()

    seed = build_seed(args)
    slug = args.slug or safe_filename(args.title)
    project_dir = VARIANTS / slug
    if project_dir.exists():
        raise SystemExit(f"Variant already exists: {project_dir}")

    write_project_files(project_dir, seed)
    print(json.dumps({
        "title": args.title,
        "path": str(project_dir),
        "seed": str(project_dir / "seed.json"),
        "outline": str(project_dir / "outline.md"),
        "characters": str(project_dir / "characters.md"),
        "cover_brief": str(project_dir / "cover_brief.json"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
