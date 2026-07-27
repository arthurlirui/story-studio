#!/usr/bin/env python3
"""Generate remaining chapters for 沉默的真相 (chapters 4-30). 5 concurrent."""
import httpx, asyncio, sys
from pathlib import Path

API_BASE = "https://llmapi.pcl.ac.cn/v1"
API_KEY = "sk-dLcQBdtUNpw5vxrSP8HjlXfJGb8nP8uYlpSMpfKKTD8QfbbS"
MODEL = "DeepSeek-V4-Pro"
BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/千行百业/variants/04_沉默的真相")
CHAPS = BASE / "knowledge" / "story" / "chapters"
OUTLINE = BASE / "knowledge" / "story" / "outline.md"
BIBLE = Path("/home/pz03-b-003-pcl/code/story-studio/series/千行百业/knowledge/series_bible.md")
STYLE = Path("/home/pz03-b-003-pcl/code/story-studio/series/千行百业/knowledge/style_guide.md")

outline_text = OUTLINE.read_text()
bible_text = BIBLE.read_text()
style_text = STYLE.read_text()

CHAP_PROMPT_TEMPLATE = """你是顶级网文作家，擅长九十年代调查记者题材，文字精准、克制、有时代厚度。

## 系列背景
{bible_section}

## 风格要求
{style_section}

## 小说大纲（节选）
{outline_section}

## 本章大纲
{chapter_outline}

## 写作要求
- 严格按照本章大纲生成正文
- 每章3000-5000字
- 第三人称有限视角，跟女主林安之走
- 标题格式：## 第N章 标题
- 开头要有钩子，结尾留悬念
- 九零年代时代感：BP机/寻呼台/公用电话/传真机/胶片相机/暗房/手写稿
- 广州地域特色：天河/石牌村/珠江/西关/南方日报社旧址/火车站
- 调查记者职业细节：暗访录音/底片保护/线人接头/蹲点/翻旧报纸/多人交叉验证
- 不要煽情、不要说教、不涉及官场仕途内容
- 只输出正文，不要任何说明/批注"""

async def gen_chapter(client, ch_num, sem):
    async with sem:
        name = f"chapter_{ch_num:03d}"
        path = CHAPS / f"{name}.md"
        if path.exists():
            existing = path.read_text()
            if len(existing) > 2500:
                print(f"  {name} SKIP (already {len(existing)} chars)")
                return 1

        lines = outline_text.split("\n")
        relevant = []
        in_chapter = False
        target = f"第{ch_num}章"
        for i, line in enumerate(lines):
            if target in line and ("**" in line or "章：" in line or "章:" in line):
                in_chapter = True
            if in_chapter:
                relevant.append(line)
                if "第" in line and str(ch_num+1) in line and "章" in line and i > 0:
                    break
        chapter_outline = "\n".join(relevant[-50:]) if relevant else ""

        prompt = CHAP_PROMPT_TEMPLATE.format(
            bible_section=bible_text[:8000],
            style_section=style_text[:6000],
            outline_section=outline_text[:12000],
            chapter_outline=chapter_outline
        )

        sys.stdout.write(f"  {name}..."); sys.stdout.flush()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
        payload = {"model": MODEL, "messages": [
            {"role": "system", "content": "你是顶级网文作家，擅长细腻克制的九十年代调查记者叙事。"},
            {"role": "user", "content": prompt}
        ], "temperature": 0.82, "max_tokens": 6000}

        for attempt in range(3):
            try:
                r = await client.post(f"{API_BASE}/chat/completions", json=payload, headers=headers, timeout=300.0)
                if r.status_code == 429:
                    await asyncio.sleep(5 * (2**attempt))
                    continue
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                if content and len(content.strip()) > 1500:
                    path.write_text(content.strip() + "\n", encoding="utf-8")
                    print(f" OK ({len(content)} chars)")
                    return 1
                print(" TOO SHORT")
                return 0
            except Exception as e:
                sys.stderr.write(f"  E: {e}\n")
                if attempt < 2:
                    await asyncio.sleep(5)
        print(" FAIL")
        return 0

async def main():
    CHAPS.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(5)
    total = 0
    async with httpx.AsyncClient() as client:
        for i in range(4, 31, 5):
            batch = range(i, min(i+5, 31))
            tasks = [gen_chapter(client, n, sem) for n in batch]
            results = await asyncio.gather(*tasks)
            total += sum(results)
            print(f"  [{min(i+4,30)}/30] batch done")
            await asyncio.sleep(2)

    merged = []
    for n in range(1, 31):
        f = CHAPS / f"chapter_{n:03d}.md"
        if f.exists():
            merged.append(f.read_text().strip())
    (BASE / "output").mkdir(parents=True, exist_ok=True)
    full_path = BASE / "output" / "沉默的真相.txt"
    full_path.write_text("\n\n".join(merged), encoding="utf-8")
    print(f"\nDONE: {total} chapters generated, merged -> {full_path}")

asyncio.run(main())
