#!/usr/bin/env python3
"""写第30章终章"""
import asyncio, httpx, json, re, sys
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
    print("📝 写第30章终章...")
    ch29_full = read_file(CHAPTERS / "chapter_029.md")
    ch29_story = extract_story(ch29_full)
    ch28_summary = read_file(SUMMARIES / "chapter_028.md")
    ch29_summary = read_file(SUMMARIES / "chapter_029.md")
    world = read_file(BASE.parent / "world" / "settings.md")[:3000]
    characters = read_file(BASE.parent / "world" / "characters.md")[:2000]

    ch30_brief = {}
    for bf in (BASE / "batch_briefs").glob("*.json"):
        try:
            data = json.loads(bf.read_text(encoding='utf-8'))
            if "30" in data.get("brief", {}):
                ch30_brief = data["brief"]["30"]
                break
        except:
            pass

    system_msg = "你是一位资深网文作家，擅长志怪灵异题材。你的文风沉郁厚重，对话精炼，善于用细节承载情感。直接输出小说正文，不要任何引导语或说明。"

    user_msg = "请撰写《十日长安》第三十章《永恒囚徒》（终章）。\n\n"
    user_msg += "## 本章大纲\n双线结局：轮回线（沈墨永恒轮回）+真实线（长安城破但无人）。这是全书终章，所有伏笔需在此回收。\n\n"
    user_msg += "## 批次协调简报（第30章）\n"
    user_msg += "入口状态：" + ch30_brief.get('entry_state', '（无）') + "\n"
    user_msg += "出口状态：" + ch30_brief.get('exit_state', '（无）') + "\n"
    user_msg += "必须揭示：" + json.dumps(ch30_brief.get('must_reveal', []), ensure_ascii=False) + "\n"
    user_msg += "禁止揭示：" + json.dumps(ch30_brief.get('must_not_reveal', []), ensure_ascii=False) + "\n"
    user_msg += "交接点：" + ch30_brief.get('handoff', '（无）') + "\n\n"
    user_msg += "## 前章（第29章）摘要\n" + ch29_summary + "\n\n"
    user_msg += "## 第29章结尾正文（衔接用）\n" + ch29_story[-2000:] + "\n\n"
    user_msg += "## 第28章摘要\n" + ch28_summary + "\n\n"
    user_msg += "## 世界观参考\n" + world + "\n\n"
    user_msg += "## 角色参考\n" + characters + "\n\n"
    user_msg += "## 终章必须完成的内容\n"
    user_msg += "1. 始神的最终去向——带着所有灵魂共同编织的新梦沉入更深的底底，不再需要外部封印\n"
    user_msg += "2. 长安城失去天府之国属性后的具体变化——龙脉共生菌群消失，土地肥力回归普通水平，但城不因此衰败，因为城的根基从来不是神而是人\n"
    user_msg += "3. 所有主要角色的最终结局：玄宗与杨贵妃（马嵬坡的梦不再轮回）、李白（从笼子中解脱）、公孙大娘（第一代封印者的倒影消散）、高力士（守护结束）、更夫（最后一次敲梆子后嘴角烙印消失）\n"
    user_msg += "4. 沈墨与阿九的灵魂连接在失去封印功能后的新形态——不再是碎片绑定，而是两人自由选择维持的连接，虎口与掌心的刀疤淡化为普通疤痕\n"
    user_msg += "5. 第七块碎片\"生\"的最终含义——不是活着的执念，而是选择活着的自由，沈墨与阿九的第三种选择成为新梦的第一条规则\n"
    user_msg += "6. 最后场景：沈墨与阿九并肩站在永宁坊废墟上，更夫梆子声从远处传来——三下，寅时。沈墨听不见梆子声，但通过阿九的一半听力，他听到了。阿九问他听到了什么。沈墨说：天亮的声音。阿九笑了。她掌心的刀疤在晨光中看起来只是一道普通的旧伤。\n\n"
    user_msg += "## 写作要求\n1. 对话用「」引号\n2. 文风沉郁厚重，细节承载情感\n3. 约4000-5000字\n4. 这是终章，所有伏笔在此回收，不留续集暗示\n5. 明确表示始神带着新梦永久沉眠\n6. 明确表示沈墨与阿九选择维持连接\n7. 只输出正文，不要标题、注释、说明"

    async with httpx.AsyncClient() as client:
        result = await call_llm(client, [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ], max_tokens=8192)

    if result:
        output = "# 第三十章 永恒囚徒\n\n" + result + "\n"
        (CHAPTERS / "chapter_030.md").write_text(output, encoding='utf-8')
        print(f"  ✅ 第30章写作完成，共 {len(result)} 字")
    else:
        print("  ❌ 第30章写作失败")

if __name__ == "__main__":
    asyncio.run(main())
