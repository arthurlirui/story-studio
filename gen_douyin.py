#!/usr/bin/env python3
import asyncio, httpx, json, sys
from pathlib import Path
import yaml

settings = yaml.safe_load(open('/home/pz03-b-003-pcl/code/story-studio/config/settings.yaml'))
API_BASE = settings.get('llm_base_url', 'https://llmapi.pcl.ac.cn/v1')
API_KEY = settings['llm_api_key']
MODEL = settings.get('main_model', 'DeepSeek-V4-Pro')

BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/抖音全民写作大赛/variants")
ideas = json.loads(Path("/home/pz03-b-003-pcl/code/story-studio/series/抖音全民写作大赛/ideas.json").read_text("utf-8"))

async def llm(client, msgs, mt=3000):
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    pl = {"model": MODEL, "messages": msgs, "temperature": 0.9, "max_tokens": mt}
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

async def gen(client, idea):
    iid = idea["id"]
    out = BASE / f'{iid}_{idea["title"]}'
    out.mkdir(parents=True, exist_ok=True)
    
    story_prompt = f"""你是抖音历史共情写作者。请写一篇关于{idea["person"]}（{idea["era"]}）的抖音图文内容。

## 开头画面（改写扩展，不要照抄）
{idea["hook"]}

## 要求
1. 字数1500-2000字，不超过2000字
2. 结构：反常识钩子开头(200字) → 关键历史细节(800字) → 情感升华(300字) → 互动收尾(100字)
3. 短句为主，每段不超过3行，适配抖音图文滑动
4. 用具体历史细节打动人，不要空洞抒情
5. 对话用「」引号
6. 结尾加互动提问
7. 关键词：{idea["keywords"]}

只输出正文，不要标题。"""

    cover_prompt = f"""为{idea["person"]}（{idea["era"]}）生成AI绘画提示词。
场景：与{idea["person"]}最代表性的历史瞬间
风格：中式水墨/工笔混合，暗色调，电影质感
只输出英文Midjourney prompt。"""

    print(f"  {iid} {idea['person']}...", end="", flush=True)
    story, cover = await asyncio.gather(
        llm(client, [{"role":"system","content":"你是历史共情写作者，文风冷峻克制有温度。"},{"role":"user","content":story_prompt}]),
        llm(client, [{"role":"system","content":"You are an AI art prompt expert."},{"role":"user","content":cover_prompt}], 800)
    )
    
    if story:
        (out / "story.md").write_text(f"# {idea['person']}·{idea['title']}\n\n{story}\n", encoding="utf-8")
    if cover:
        (out / "cover_prompt.txt").write_text(cover, encoding="utf-8")
    (out / "meta.yaml").write_text(f"id: {iid}\ntitle: {idea['title']}\nperson: {idea['person']}\nera: {idea['era']}\n", encoding="utf-8")
    print(f" done ({len(story)}字)")

async def main():
    print(f"🚀 生成 {len(ideas)} 篇内容...")
    async with httpx.AsyncClient() as client:
        # 4 at a time to avoid rate limit
        for i in range(0, len(ideas), 4):
            batch = ideas[i:i+4]
            await asyncio.gather(*[gen(client, idea) for idea in batch])
    print("✅ 全部完成")

if __name__ == "__main__":
    asyncio.run(main())
