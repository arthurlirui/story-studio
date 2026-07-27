#!/usr/bin/env python3
import asyncio, httpx, json, sys, re
from pathlib import Path

API_BASE = "BASE_PLACEHOLDER"
API_KEY = "KEY_PLACEHOLDER"
MODEL = "MODEL_PLACEHOLDER"

BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/抖音全民写作大赛/variants")

async def llm(client, msgs, mt=4500):
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    pl = {"model": MODEL, "messages": msgs, "temperature": 0.85, "max_tokens": mt}
    for i in range(3):
        try:
            r = await client.post(f"{API_BASE}/chat/completions", json=pl, headers=h, timeout=300.0)
            if r.status_code == 429:
                await asyncio.sleep(5*(2**i)); continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  retry {i+1}: {e}", file=sys.stderr)
            if i < 2: await asyncio.sleep(5)
    return ""

POLISH_PROMPT = """你是中国顶级的文字编辑和文学润色专家。请对以下抖音历史图文文案进行深度润色。

## 润色目标
1. **语言精妙**：动词要精准有力，形容词要新鲜不落俗套。用具体替代抽象，用感官替代概念。例：不说"他很伤心"，说"他的眼眶像被刀子剜了一下"。
2. **节奏感**：长短句交替，如呼吸般自然。短句有力，长句铺陈。偶尔一个字的段落，像一记闷拳。
3. **金句设计**：每篇至少3-5个可被截图传播的金句。金句特征：意料之外情理之中，用最少的字说最重的话。例："他以为自己在铸造一个国家的脊梁，却不知道自己也在铸造一副困住自己的枷锁。"
4. **钩子强化**：开头前三句必须让人放不下手机。用反常识、悬念、或画面感极强的场景切入。不要用"你大概想不到"这类套路。
5. **文学性**：从"内容"提升到"文学"。用隐喻、通感、反讽、留白等手法。但不堆砌辞藻，克制比华丽更重要。
6. **画面感**：每个关键场景要有电影级的画面感。光影、声音、温度、气味，让读者"看见"。
7. **历史准确**：不改变历史事实，不编造史料。可以合理想象细节，但不能违背已知史实。
8. **保持原有结构**：不改变原文的叙事顺序和核心信息，只提升语言质量。
9. **字数控制**：润色后字数不超过原文的120%，也不少于80%。
10. **格式统一**：段落之间空行分隔，不用诗化断句（不要每行一断），用正常散文段落格式。

## 原文
{story}

## 输出要求
只输出润色后的正文（含标题行），不要任何说明、批注或解释。"""

async def polish_one(client, d):
    story_path = d / "story.md"
    if not story_path.exists():
        return
    original = story_path.read_text("utf-8")
    if not original.strip():
        return
    
    lines = original.strip().split(chr(10))
    title_line = lines[0] if lines[0].startswith("#") else ""
    body = chr(10).join(lines[1:]).strip()
    
    prompt = POLISH_PROMPT.replace("{story}", body)
    
    print(f"  {d.name}...", end="", flush=True)
    polished = await llm(client, [
        {"role": "system", "content": "你是顶级文学编辑，擅长将好的历史故事提升为精妙的文学作品。你的文字冷峻克制有力量，像刀刻一样精确。"},
        {"role": "user", "content": prompt}
    ], 4500)
    
    if polished and len(polished.strip()) > 100:
        if not polished.startswith("#"):
            polished = f"{title_line}{chr(10)}{chr(10)}{polished}"
        story_path.write_text(polished.strip() + chr(10), encoding="utf-8")
        print(f" done ({len(polished)}字)")
    else:
        print(f" SKIP (too short)")

async def main():
    dirs = sorted([d for d in BASE.iterdir() if d.is_dir() and d.name[0:2].isdigit()])
    print(f"润色 {len(dirs)} 篇文案...")
    async with httpx.AsyncClient() as client:
        for i in range(0, len(dirs), 5):
            batch = dirs[i:i+5]
            await asyncio.gather(*[polish_one(client, d) for d in batch])
            print(f"  --- batch {i//5+1}/{(len(dirs)-1)//5+1} done ---")
    print("全部润色完成")

if __name__ == "__main__":
    asyncio.run(main())
