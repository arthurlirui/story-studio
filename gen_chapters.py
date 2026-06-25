#!/usr/bin/env python3
"""
逐章生成《玉璧之战》(第2-9章)，使用 Volcengine API + 延迟避免限流。
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

API_BASE = "https://ark.cn-beijing.volces.com/api/coding/v3"
API_KEY = "ark-cbb53828-980b-4d51-89c3-215947aa79f1-62bef"
MODEL = "ark-code-latest"
OUTPUT_DIR = Path("/data/openclaw/workspace/story-studio/玉璧之战")

# Load outline
OUTLINE = (OUTPUT_DIR / "03_大纲.md").read_text(encoding="utf-8")
SETTINGS = (OUTPUT_DIR / "02_设定.md").read_text(encoding="utf-8")

SYSTEM_PROMPT = """# 你是谁

你是 **场景编剧 (Scene Writer)**，创作团队的核心写作者。你把大纲变成生动的文字，把角色设定变成鲜活的对话和行动。

# 写作原则

## 展示，不要告诉 (Show, Don't Tell)
❌ "他很生气"
✅ "他的拳头握得指节发白，太阳穴突突跳动"

## 感官描写
- 不止是视觉——声音、气味、触觉、温度
- 每一段场景至少包含 2 种感官

## 节奏控制
- 紧张场景: 短句、短段落、快节奏
- 舒缓场景: 长句、描写丰富、慢节奏
- 高潮部分: 对话简短，行动密集

## 章节结构
- 开场: 钩子（1-2段）
- 发展: 冲突/对话/探索
- 高潮: 章节核心事件
- 结尾: 钩子/悬念/转折

# 输出要求
- 每章 2000-3500 字
- 使用第三人称有限视角
- 段落不要太长（每段 3-5 句为宜）
- 对话单独成段
- 章节末尾必须有悬念或钩子
- 直接输出章节正文，不要加"第X章"标题之外的任何说明"""


async def generate_chapter(chapter_num: int, prev_chapter_text: str = "") -> str:
    """生成单章."""
    # Extract this chapter's outline
    chapter_marker = f"## 第{chapter_num}章" if chapter_num < 10 else f"## 第{chapter_num}章"
    # Try different patterns
    for marker in [
        f"## 第{chapter_num}章",
        f"## 第 {chapter_num} 章",
        f"## 第{self._num_to_cn(chapter_num)}章",
    ]:
        if marker in OUTLINE:
            break

    # Build prompt
    prompt = f"""请根据以下设定和大纲，撰写《玉璧之战》第 {chapter_num} 章的完整正文。

## 创作要求
- 荡气回肠、高潮迭起
- 突出战争残酷和英雄宿命感
- 高欢的"差一点就成功"的遗憾，韦孝宽的"拼尽全力顶着巨大压力"
- 英雄史诗的宏大场面
- 每章必须有高潮和爽点

## 世界观与角色设定
{SETTINGS[:3000]}

## 章节大纲
{OUTLINE}

{f"## 前一章内容参考\n{prev_chapter_text[:1500]}" if prev_chapter_text else ""}

---

请直接输出第 {chapter_num} 章的完整正文（2000-3500字），以"# 第{chapter_num}章"开头。"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "max_tokens": 8192,
    }

    max_retries = 8
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    f"{API_BASE}/chat/completions",
                    json=payload,
                    headers=headers,
                )

            if resp.status_code == 429:
                delay = min(5 * (2 ** attempt), 120)
                print(f"  Rate limited, waiting {delay}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        except Exception as e:
            print(f"  Error: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(10)
            else:
                return f"[Error: {e}]"

    return "[Failed after all retries]"


async def main():
    chapters_to_generate = list(range(2, 10))  # Chapters 2-9

    prev_text = ""
    for ch in chapters_to_generate:
        print(f"\n{'='*40}")
        print(f"Generating Chapter {ch}...")
        print(f"{'='*40}")

        text = await generate_chapter(ch, prev_text)
        prev_text = text

        # Save
        path = OUTPUT_DIR / f"04_第{ch}章.md"
        path.write_text(f"# 第 {ch} 章\n\n{text}", encoding="utf-8")
        print(f"  Saved: {path} ({len(text)} chars)")

        # Wait between chapters to avoid rate limits
        if ch < 9:
            print(f"  Waiting 8s before next chapter...")
            await asyncio.sleep(8)

    print(f"\n{'='*40}")
    print("All chapters generated!")
    print(f"{'='*40}")


if __name__ == "__main__":
    asyncio.run(main())
