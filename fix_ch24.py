#!/usr/bin/env python3
"""补写第24章截断部分"""
import asyncio, httpx, re, sys
from pathlib import Path
import yaml

settings = yaml.safe_load(open('/home/pz03-b-003-pcl/code/story-studio/config/settings.yaml'))
API_BASE = settings.get('llm_base_url', 'https://llmapi.pcl.ac.cn/v1')
API_KEY = settings.get('llm_api_key', '')
MODEL = settings.get('main_model', 'DeepSeek-V4-Pro')

BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/轮回怪谈/variants/01_十日长安/knowledge/story")
CHAPTERS = BASE / "chapters"
SUMMARIES = BASE / "summaries"

def extract_story(md_text):
    lines = md_text.split('\n')
    story = []
    for line in lines:
        if line.startswith('>'):
            story.append(line[1:].strip())
    return '\n'.join(story)

def read_file(path):
    p = Path(path)
    return p.read_text(encoding='utf-8') if p.exists() else ""

async def call_llm(client, messages, max_tokens=8192):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    payload = {"model": MODEL, "messages": messages, "temperature": 0.9, "max_tokens": max_tokens}
    for attempt in range(3):
        try:
            resp = await client.post(f"{API_BASE}/chat/completions", json=payload, headers=headers, timeout=600.0)
            if resp.status_code == 429:
                print(f"  Rate limited, retry in {5*(2**attempt)}s", file=sys.stderr)
                await asyncio.sleep(5 * (2 ** attempt))
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < 2:
                await asyncio.sleep(5)
    return ""

async def main():
    print("📝 补写第24章...")
    ch24_full = read_file(CHAPTERS / "chapter_024.md")
    ch24_story = extract_story(ch24_full)
    ch23_summary = read_file(SUMMARIES / "chapter_023.md")
    ch25_summary = read_file(SUMMARIES / "chapter_025.md")
    ch24_summary = read_file(SUMMARIES / "chapter_024.md")
    world = read_file(BASE.parent / "world" / "settings.md")[:3000]
    characters = read_file(BASE.parent / "world" / "characters.md")[:2000]

    system_msg = "你是一位资深网文作家，擅长志怪灵异题材。你的文风沉郁厚重，对话精炼，善于用细节承载情感。直接输出小说正文，不要任何引导语或说明。"

    user_msg = "请续写《十日长安》第二十四章《我记得每一轮的你》。\n\n"
    user_msg += "## 本章大纲\n阿九亲自揭示：她记得一切，是长安城的灵魂碎片。本章核心是阿九向沈墨坦白她记得每一轮的真相。\n\n"
    user_msg += "## 前情（第23章摘要）\n" + ch23_summary + "\n\n"
    user_msg += "## 本章已有正文（写到一半截断了，请从这里续写）\n" + ch24_story[-3000:] + "\n\n"
    user_msg += "本章摘要预期：" + ch24_summary + "\n\n"
    user_msg += "## 续写要点\n"
    user_msg += "1. 阿九揭示\"一张白纸\"的深层含义——她自己也是白纸，每一轮都被重写\n"
    user_msg += "2. 阿九反向读出玉璧螺旋铭文的第三层——隐藏的造人动机：守墓人造锚点不是为了封印始神，是为了给自己留一个\"可以叫名字的人\"\n"
    user_msg += "3. 第三层铭文最后三个字：\"叫我的名字\"——始神的请求，不是命令\n"
    user_msg += "4. 沈墨理解了：始神不是在愤怒，是在等人叫它的名字。叫出真名，碎片融化，契约解除\n"
    user_msg += "5. 沈墨叫出真名\"长\"——阿九给自己取的名字，也是始神的真名\n"
    user_msg += "6. 七块碎片同时融化，玉璧化作金色液体流入地面，太液池底传来震动——始神翻身\n"
    user_msg += "7. 阿九从怀中取出更夫的梆子，为第25章做铺垫\n"
    user_msg += "8. 结尾钩子：阿九说\"封印破了，但不是我们破的。是他自己醒的。\"\n\n"
    user_msg += "## 下一章（第25章）摘要\n" + ch25_summary + "\n\n"
    user_msg += "## 世界观参考\n" + world + "\n\n"
    user_msg += "## 角色参考\n" + characters + "\n\n"
    user_msg += "## 写作要求\n1. 直接从截断处续写，不要重复已有内容\n2. 对话用「」引号\n3. 文风沉郁厚重，细节承载情感\n4. 续写约3000-4000字\n5. 以章节钩子结尾\n6. 只输出正文，不要标题、注释、说明"

    async with httpx.AsyncClient() as client:
        result = await call_llm(client, [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ], max_tokens=8192)

    if result:
        full_story = ch24_story + "\n\n" + result
        output = "# 第二十四章 我记得每一轮的你\n\n" + full_story + "\n"
        (CHAPTERS / "chapter_024.md").write_text(output, encoding='utf-8')
        print(f"  ✅ 第24章补写完成，共 {len(full_story)} 字")
    else:
        print("  ❌ 第24章补写失败")

if __name__ == "__main__":
    asyncio.run(main())
