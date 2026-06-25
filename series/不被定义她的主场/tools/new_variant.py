#!/usr/bin/env python3
"""Create a new long-form novel variant under the 《不被定义她的主场》 series."""
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
    "era": "年代",
    "fantasy": "幻言",
    "wasteland": "废土",
    "infinite": "无限流",
}

ENDING_LABELS = {
    "career_ascension": "事业登顶",
    "freedom_life": "自由生活",
    "collective_change": "群体改变",
    "power_rebuild": "权力重构",
    "relationship_rebuild": "关系重建",
}


def safe_filename(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", s.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "untitled")[:max_len]


def build_seed(args: argparse.Namespace) -> dict:
    seed = json.loads((TEMPLATES / "novel_seed_template.json").read_text(encoding="utf-8"))
    seed.update({
        "series": "不被定义她的主场",
        "title": args.title,
        "mode": args.mode,
        "definition": args.definition,
        "core_statement": args.core,
        "logline": args.logline or f"{MODE_LABELS.get(args.mode, args.mode)}长篇。女主被'{args.label}'定义，却以'{args.core}'为主线，建立自己的主场。",
        "conflict_engine": args.conflict_engine,
        "ending": args.ending,
        "opening_hook": args.hook,
        "cover_direction": args.cover_direction,
    })
    seed["heroine"].update({
        "name": args.heroine_name,
        "archetype": args.heroine_archetype,
        "initial_label": args.label,
        "visible_goal": args.goal,
        "skill_or_power": args.skill,
        "main_arena": args.arena,
    })
    seed["antagonist_system"].update({
        "system_name": args.system,
        "definition_imposed": args.label,
    })
    return seed


def write_project(project_dir: Path, seed: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "chapters").mkdir(exist_ok=True)

    (project_dir / "seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(TEMPLATES / "volume_outline_template.md", project_dir / "outline.md")
    shutil.copy2(TEMPLATES / "character_sheet_template.md", project_dir / "characters.md")
    shutil.copy2(TEMPLATES / "chapter_template.md", project_dir / "chapter_template.md")

    cover = json.loads((TEMPLATES / "cover_brief_template.json").read_text(encoding="utf-8"))
    cover["title"] = seed["title"]
    cover["subtitle"] = "女子就是好"
    cover["genre"] = f"Chinese {MODE_LABELS.get(seed['mode'], seed['mode'])} female empowerment novel"
    cover["core_visual"] = seed.get("cover_direction") or cover["core_visual"]
    (project_dir / "cover_brief.json").write_text(json.dumps(cover, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# {seed['title']}

- 系列：不被定义她的主场
- 模式：{seed['mode']} / {MODE_LABELS.get(seed['mode'], seed['mode'])}
- 不被定义方向：{seed['definition']}
- 女主原型：{seed['heroine']['archetype']}
- 冲突发动机：{seed['conflict_engine']}
- 结局路线：{seed['ending']} / {ENDING_LABELS.get(seed['ending'], seed['ending'])}

## 一句话

{seed['logline']}

## 核心立意

{seed['core_statement']}

## 关联知识库

- ../../knowledge/series_bible.md
- ../../knowledge/definition_modes.md
- ../../knowledge/world_modes.md
- ../../knowledge/heroine_archetypes.md
- ../../knowledge/female_relationships.md
- ../../knowledge/conflict_engines.md
- ../../knowledge/style_guide.md
- ../../knowledge/continuity_rules.md

## 推荐流程

1. 完成 characters.md。
2. 完成 outline.md 四卷大纲。
3. 生成 chapter_plan.md，每章标注爽点和小高潮。
4. 输出 chapters/ 正文。
5. 用 cover_brief.json 生成封面。
"""
    (project_dir / "README.md").write_text(readme, encoding="utf-8")

    continuity = f"""# 连续性记录：{seed['title']}

## 固定事实

- 女主被定义为：{seed['heroine']['initial_label']}
- 女主主动目标：{seed['heroine']['visible_goal']}
- 女主能力/方法论：{seed['heroine']['skill_or_power']}
- 女主主场：{seed['heroine']['main_arena']}

## 待补充

- [ ] 女主关键失败与复盘
- [ ] 女性盟友群像
- [ ] 旧规则代表人物
- [ ] 主场建立标志
- [ ] 结局画面
"""
    (project_dir / "continuity_log.md").write_text(continuity, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a new 《不被定义她的主场》 long-form novel variant.")
    ap.add_argument("--title", required=True)
    ap.add_argument("--mode", choices=list(MODE_LABELS), required=True)
    ap.add_argument("--definition", default="D01+D04", help="D01-D07 or combination")
    ap.add_argument("--core", required=True, help="Core statement of 'not being defined'")
    ap.add_argument("--heroine-name", default="待定女主")
    ap.add_argument("--heroine-archetype", default="H01")
    ap.add_argument("--label", default="别人强加给她的标签")
    ap.add_argument("--goal", default="建立自己的主场")
    ap.add_argument("--skill", default="专业能力与持续行动")
    ap.add_argument("--arena", default="待定主场")
    ap.add_argument("--system", default="旧规则与偏见系统")
    ap.add_argument("--conflict-engine", default="CE01")
    ap.add_argument("--ending", choices=list(ENDING_LABELS), default="career_ascension")
    ap.add_argument("--hook", default="所有人都认为她不该站上这个位置，她偏偏第一个解决了问题。")
    ap.add_argument("--cover-direction", default="女主站在自己的主场中央，所有目光向她汇聚")
    ap.add_argument("--logline", default="")
    ap.add_argument("--slug", default="")
    args = ap.parse_args()

    seed = build_seed(args)
    slug = args.slug or safe_filename(args.title)
    project_dir = VARIANTS / slug
    if project_dir.exists():
        raise SystemExit(f"Variant already exists: {project_dir}")

    write_project(project_dir, seed)
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
