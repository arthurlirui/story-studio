#!/usr/bin/env python3
"""
🎭 风格润色脚本 — 使用 Qwen3.5-9B + LoRA 对小说进行风格化润色

用法:
    python3 run_style_polish.py <input_file> [--style moyan] [--output <path>]
    python3 run_style_polish.py /data/openclaw/workspace/story-studio/daily_novels/output/2026-06-22_1305_粽香人海.txt --style moyan
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.style_polisher import StylePolisher, STYLE_REGISTRY, list_styles
from agents.local_inference_client import LocalInferenceClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("style-polish")


async def main():
    parser = argparse.ArgumentParser(description="风格润色 — Qwen3.5-9B + LoRA")
    parser.add_argument("input", help="输入文件路径")
    parser.add_argument("--style", default="moyan", help="风格名称 (moyan/murakami)")
    parser.add_argument("--output", default=None, help="输出文件路径 (默认同名加 _{style}_polished)")
    parser.add_argument("--chunk_size", type=int, default=1200, help="分块字数")
    parser.add_argument("--temperature", type=float, default=None, help="生成温度 (默认用风格配置)")
    parser.add_argument("--max_tokens", type=int, default=None, help="每块最大生成token数")
    parser.add_argument("--list", action="store_true", help="列出可用风格后退出")
    args = parser.parse_args()

    if args.list:
        print("\n可用风格:")
        for s in list_styles():
            print(f"  • {s['key']:12s} — {s['name']}: {s['description']}")
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        sys.exit(1)

    # Check style exists
    if args.style not in STYLE_REGISTRY:
        print(f"❌ 未知风格 '{args.style}'，可用: {', '.join(STYLE_REGISTRY.keys())}")
        sys.exit(1)

    style_config = STYLE_REGISTRY[args.style]

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_{args.style}_polished{input_path.suffix}"

    print(f"\n{'='*60}")
    print(f"🎭 风格润色引擎")
    print(f"{'='*60}")
    print(f"  输入:   {input_path}")
    print(f"  风格:   {args.style} ({style_config['name']})")
    print(f"  基座:   {style_config['base_model']}")
    print(f"  LoRA:   {style_config['lora_path']}")
    print(f"  输出:   {output_path}")
    print(f"  分块:   {args.chunk_size} 字/块")
    print(f"  温度:   {args.temperature or style_config['temperature']}")
    print(f"{'='*60}\n")

    # Read input
    text = input_path.read_text(encoding="utf-8")
    print(f"📖 原文长度: {len(text)} 字\n")

    # Initialize local inference client
    print("🔧 初始化本地推理客户端 (加载 Qwen3.5-9B + LoRA)...")
    print("   ⏳ 首次加载需要一些时间（模型 ~9B 参数）...\n")

    client = LocalInferenceClient.from_style(style=args.style)

    # Create polisher
    polisher = StylePolisher(
        client=client,
        style=args.style,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    print(f"✅ 模型已加载 — 风格: {style_config['name']}\n")

    # Polish
    print("✍️  开始润色...\n")

    extra_instruction = (
        "这是一篇关于端午节的现实主义小说。"
        "请保持故事的核心情节和人物关系不变，"
        "在语言层面进行莫言风格化——"
        "让叙述更有泥土感、感官更饱和、比喻更奇诡，"
        "对话更鲜活泼辣，叙事节奏更富张力。"
    )

    result = await polisher.polish(
        text=text,
        instruction=extra_instruction,
        chunk_size=args.chunk_size,
    )

    # Save
    output_path.write_text(result, encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"✅ 润色完成!")
    print(f"   原文:   {len(text)} 字")
    print(f"   润色后: {len(result)} 字")
    print(f"   输出:   {output_path}")
    print(f"{'='*60}\n")

    # Show preview
    print("📋 润色预览 (前 1500 字):\n")
    print(result[:1500])
    print("\n...")


if __name__ == "__main__":
    asyncio.run(main())
