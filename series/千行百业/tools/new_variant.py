#!/usr/bin/env python3
"""快速创建《千行百业》系列新变体"""

import argparse
import json
import os
import sys

SERIES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARIANTS_DIR = os.path.join(SERIES_DIR, "variants")
TEMPLATES_DIR = os.path.join(SERIES_DIR, "templates")
SEED_TEMPLATE = os.path.join(TEMPLATES_DIR, "novel_seed_template.json")


def slugify(text):
    """简单中文转拼音 slug 或直接用编号"""
    return text.replace(" ", "_").replace("《", "").replace("》", "")


def create_variant(args):
    # 读取已有变体编号
    existing = [d for d in os.listdir(VARIANTS_DIR) if os.path.isdir(os.path.join(VARIANTS_DIR, d))]
    number = len(existing) + 1
    prefix = f"{number:02d}"

    # 读取种子模板
    with open(SEED_TEMPLATE, "r", encoding="utf-8") as f:
        seed = json.load(f)

    # 填充种子
    seed["title"] = args.title
    seed["slug"] = prefix
    seed["profession"] = args.profession
    seed["city"] = args.city
    seed["era"] = args.era
    seed["core_conflict"] = args.core
    seed["one_line"] = args.one_line or args.core

    seed["protagonist"]["profession"] = args.profession
    seed["protagonist"]["professional_dilemma"] = args.core

    # 创建目录
    variant_dir = os.path.join(VARIANTS_DIR, prefix)
    os.makedirs(variant_dir, exist_ok=True)

    # 写入种子
    seed_path = os.path.join(variant_dir, "seed.json")
    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False, indent=2)

    # 创建空白大纲
    outline_path = os.path.join(variant_dir, "outline.md")
    with open(outline_path, "w", encoding="utf-8") as f:
        f.write(f"# {args.title}\n\n")
        f.write(f"- 职业：{args.profession}\n")
        f.write(f"- 城市：{args.city}\n")
        f.write(f"- 年代：{args.era}\n")
        f.write(f"- 核心冲突：{args.core}\n\n")
        f.write("## 大纲\n\n")
        f.write("> 待填充\n")

    # 创建章节目录
    chapters_dir = os.path.join(variant_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    print(f"✅ 已创建变体 #{number}: {args.title}")
    print(f"   目录: {variant_dir}")
    print(f"   种子: {seed_path}")
    print(f"   大纲: {outline_path}")
    print(f"   章节: {chapters_dir}/")


def main():
    parser = argparse.ArgumentParser(description="创建《千行百业》系列新变体")
    parser.add_argument("--title", required=True, help="书名")
    parser.add_argument("--profession", required=True, help="职业")
    parser.add_argument("--city", default="上海", help="城市")
    parser.add_argument("--era", default="当代", help="年代")
    parser.add_argument("--core", required=True, help="核心冲突")
    parser.add_argument("--one-line", default="", help="一句话卖点")
    create_variant(parser.parse_args())


if __name__ == "__main__":
    main()