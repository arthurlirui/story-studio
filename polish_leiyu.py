#!/usr/bin/env python3
"""Polish 雷雨请绕飞 — all 30 chapters, 5 concurrent."""
import asyncio, httpx, sys
from pathlib import Path

API_BASE = "https://llmapi.pcl.ac.cn/v1"
API_KEY = "sk-dLcQBdtUNpw5vxrSP8HjlXfJGb8nP8uYlpSMpfKKTD8QfbbS"
MODEL = "DeepSeek-V4-Pro"
BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/千行百业/variants/03_雷雨请绕飞")
SRC = BASE / "knowledge" / "story" / "chapters"
DST = BASE / "polished"
PROMPT = open("/home/pz03-b-003-pcl/code/story-studio/polish_prompt.txt").read().strip()

async def llm(client, msgs, max_tokens=6000):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    payload = {"model": MODEL, "messages": msgs, "temperature": 0.82, "max_tokens": max_tokens}
    for attempt in range(3):
        try:
            r = await client.post(f"{API_BASE}/chat/completions", json=payload, headers=headers, timeout=300.0)
            if r.status_code == 429:
                wait = 5 * (2 ** attempt)
                print(f"  rate-limited, waiting {wait}s...", flush=True)
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            sys.stderr.write(f"  retry {attempt+1}: {e}\n")
            if attempt < 2:
                await asyncio.sleep(5)
    return ""

async def polish_one(client, ch_path, sem):
    async with sem:
        name = ch_path.stem
        sys.stdout.write(f"  {name}..."); sys.stdout.flush()
        raw = ch_path.read_text("utf-8")
        if not raw.strip():
            print(" EMPTY")
            return 0
        # estimate max_tokens: roughly chars * 1.3 for Chinese token expansion + safety margin
        char_count = len(raw)
        prompt = PROMPT.replace("{chapter}", raw)
        # max output tokens: original content length estimate, capped
        out_tokens = min(max(int(char_count * 0.7), 600), 6000)

        result = await llm(client, [
            {"role": "system", "content": "你是顶级网文编辑，文字冷峻克制有张力，擅长用细节和节奏感抓住读者。精通航空管制专业题材。"},
            {"role": "user", "content": prompt}
        ], out_tokens)
        if result and len(result.strip()) > 200:
            DST.mkdir(parents=True, exist_ok=True)
            out_path = DST / f"{name}.md"
            out_path.write_text(result.strip() + "\n", encoding="utf-8")
            print(f" OK ({len(result)} chars)")
            return 1
        print(" SKIP")
        return 0

async def main():
    chapters = sorted(SRC.glob("chapter_*.md"))
    if not chapters:
        print("No chapters found!", file=sys.stderr)
        return
    total = len(chapters)
    print(f"Polishing {total} chapters of 雷雨请绕飞...")
    print("=" * 50)

    sem = asyncio.Semaphore(5)
    done = 0

    async with httpx.AsyncClient() as client:
        for i in range(0, total, 5):
            batch = chapters[i:i+5]
            results = await asyncio.gather(*[polish_one(client, ch, sem) for ch in batch])
            done += sum(results)
            print(f"  [{i+len(batch)}/{total}] {sum(results)}/{len(batch)} in batch")
            # small pause between batches
            await asyncio.sleep(2)

    # Merge into single file
    merged = []
    for ch in sorted(DST.glob("chapter_*.md")):
        merged.append(ch.read_text("utf-8").strip())
    full = "\n\n".join(merged)
    full_path = BASE / "雷雨请绕飞_润色版.txt"
    full_path.write_text(full, encoding="utf-8")
    print(f"\nDONE: {done}/{total} polished, merged → {full_path}")

asyncio.run(main())
