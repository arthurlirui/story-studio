#!/usr/bin/env python3
"""快速创建《哥伦布计划美联储》系列新变体"""

import argparse
import json
import os
import sys

SERIES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARIANTS_DIR = os.path.join(SERIES_DIR, "variants")
TEMPLATES_DIR = os.path.join(SERIES_DIR, "templates")


def create_variant(args):
    existing = [d for d in os.listdir(VARIANTS_DIR) if os.path.isdir(os.path.join(VARIANTS_DIR, d))]
    number = len(existing) + 1
    prefix = f"{number:02d}"

    variant_dir = os.path.join(VARIANTS_DIR, prefix)
    os.makedirs(variant_dir, exist_ok=True)

    seed = {
        "series": "哥伦布计划美联储",
        "title": args.title,
        "slug": prefix,
        "era": args.era,
        "family": args.family,
        "core_conflict": args.core,
        "one_line": args.one_line or args.core,
        "length": args.length
    }
    seed_path = os.path.join(variant_dir, "seed.json")
    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False, indent=2)

    outline = os.path.join(variant_dir, "outline.md")
    with open(outline, "w", encoding="utf-8") as f:
        f.write(f"# {args.title}\n\n")
        f.write(f"- 年代：{args.era}\n")
        f.write(f"- 家族：{args.family}\n")
        f.write(f"- 核心冲突：{args.core}\n\n")
        f.write("## 大纲\n\n> 待填充\n")

    chapters_dir = os.path.join(variant_dir, "chapters")
    os.makedirs(chapters_dir, exist_ok=True)

    print(f"✅ 已创建变体 #{number}: {args.title}")
    print(f"   目录: {variant_dir}")


def main():
    parser = argparse.ArgumentParser(description="创建《哥伦布计划美联储》系列新变体")
    parser.add_argument("--title", required=True, help="书名")
    parser.add_argument("--era", default="1910s", help="年代")
    parser.add_argument("--family", required=True, help="核心家族")
    parser.add_argument("--core", required=True, help="核心冲突")
    parser.add_argument("--one-line", default="", help="一句话卖点")
    parser.add_argument("--length", default="short", help="篇幅：short/long")
    create_variant(parser.parse_args())


if __name__ == "__main__":
    main()