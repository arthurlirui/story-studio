#!/usr/bin/env python3
import asyncio, httpx, sys
from pathlib import Path

API_BASE = "https://llmapi.pcl.ac.cn/v1"
API_KEY = "sk-dLcQBdtUNpw5vxrSP8HjlXfJGb8nP8uYlpSMpfKKTD8QfbbS"
MODEL = "DeepSeek-V4-Pro"
BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/千行百业/variants")
PROMPT = open("/home/pz03-b-003-pcl/code/story-studio/polish_prompt.txt").read().strip()

async def llm(c, msgs, mt=4500):
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    p = {"model": MODEL, "messages": msgs, "temperature": 0.82, "max_tokens": mt}
    for i in range(3):
        try:
            r = await c.post(f"{API_BASE}/chat/completions", json=p, headers=h, timeout=300.0)
            if r.status_code == 429:
                await asyncio.sleep(5*(2**i))
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            sys.stderr.write(f"  retry {i+1}: {e}\n")
            if i < 2:
                await asyncio.sleep(5)
    return ""

async def polish(c, ch, sem):
    async with sem:
        txt = ch.read_text("utf-8")
        if not txt.strip():
            return 0
        pr = PROMPT.replace("{chapter}", txt)
        nm = ch.stem
        print(f"  {nm}...", end="", flush=True)
        out = await llm(c, [
            {"role": "system", "content": "你是顶级网文编辑，文字冷峻克制有张力，擅长用细节和节奏感抓住读者。精通医疗航空法律等专业题材。"},
            {"role": "user", "content": pr}
        ], 4500)
        if out and len(out.strip()) > 200:
            ch.write_text(out.strip() + "\n", encoding="utf-8")
            print(f" ok ({len(out)})")
            return 1
        print(" SKIP")
        return 0

async def main():
    sem = asyncio.Semaphore(5)
    vs = sorted([d for d in BASE.iterdir() if d.is_dir()])
    tc = tp = 0
    for v in vs:
        cd = v / "knowledge" / "story" / "chapters"
        if not cd.exists():
            continue
        cs = sorted(cd.glob("chapter_*.md"))
        if not cs:
            continue
        print("=" * 50)
        print(v.name + " -- " + str(len(cs)) + " ch")
        print("=" * 50)
        tc += len(cs)
        for i in range(0, len(cs), 5):
            bt = cs[i:i+5]
            async with httpx.AsyncClient() as client:
                rs = await asyncio.gather(*[polish(client, ch, sem) for ch in bt])
            tp += sum(rs)
            print(f"  batch {i//5+1}/{(len(cs)-1)//5+1}")
    print(f"DONE: {tc} chapters, {tp} polished")

asyncio.run(main())
