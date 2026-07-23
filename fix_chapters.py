#!/usr/bin/env python3
"""补写第24章（续写截断部分）和第30章（终章）"""
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

async def fix_ch24(client):
    print("📝 补写第24章...")
    ch24_full = read_file(CHAPTERS / "chapter_024.md")
    ch24_story = extract_story(ch24_full)
    ch23_summary = read_file(SUMMARIES / "chapter_023.md")
    ch25_summary = read_file(SUMMARIES / "chapter_025.md")
    ch24_summary = read_file(SUMMARIES / "chapter_024.md")
    world = read_file(BASE.parent / "world" / "settings.md")
    characters = read_file(BASE.parent / "world" / "characters.md")

    system_msg = "你是一位资深网文作家，擅长志怪灵异题材。你的文风沉郁厚重，对话精炼，善于用细节承载情感。直接输出小说正文，不要任何引导语或说明。"

    user_msg = f"""请续写《十日长安》第二十四章《我记得每一轮的你》。

## 本章大纲
阿九亲自揭示：她记得一切，是长安城的灵魂碎片。本章核心是阿九向沈墨坦白她记得每一轮的真相。

## 前情（第23章摘要）
{ch23_summary}

## 本章已有正文（写到一半截断了，请从这里续写）
{ch24_story[-3000:]}

## 本章应有的后续情节（根据摘要）
{ch24_summary}

## 续写要点
1. 阿九揭示"一张白纸"的深层含义——她自己也是白纸，每一轮都被重写
2. 阿九反向读出玉璧螺旋铭文的第三层——隐藏的造人动机：守墓人造锚点不是为了封印始神，是为了给自己留一个"可以叫名字的人"
3. 第三层铭文最后三个字："叫我的名字"——始神的请求，不是命令
4. 沈墨理解了：始神不是在愤怒，是在等人叫它的名字。叫出真名，碎片融化，契约解除
5. 沈墨叫出真名"长"——阿九给自己取的名字，也是始神的真名
6. 七块碎片同时融化，玉璧化作金色液体流入地面，太液池底传来震动——始神翻身
7. 阿九从怀中取出更夫的梆子，为第25章做铺垫
8. 结尾钩子：阿九说"封印破了，但不是我们破的。是他自己醒的。"

## 下一章（第25章）摘要
{ch25_summary}

## 世界观参考
{world[:3000]}

## 角色参考
{characters[:2000]}

## 写作要求
1. 直接从截断处续写，不要重复已有内容
2. 对话用「」引号
3. 文风沉郁厚重，细节承载情感
4. 续写约3000-4000字
5. 以章节钩子结尾
6. 只输出正文，不要标题、注释、说明"""

    result = await call_llm(client, [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg}
    ], max_tokens=8192)

    if result:
        full_story = ch24_story + "\n\n" + result
        output = f"# 第二十四章 我记得每一轮的你\n\n{full_story}\n"
        (CHAPTERS / "chapter_024.md").write_text(output, encoding='utf-8')
        print(f"  ✅ 第24章补写完成，共 {len(full_story)} 字")
        return True
    else:
        print("  ❌ 第24章补写失败")
        return False

async def write_ch30(client):
    print("📝 写第30章终章...")
    ch29_full = read_file(CHAPTERS / "chapter_029.md")
    ch29_story = extract_story(ch29_full)
    ch28_summary = read_file(SUMMARIES / "chapter_028.md")
    ch29_summary = read_file(SUMMARIES / "chapter_029.md")
    world = read_file(BASE.parent / "world" / "settings.md")
    characters = read_file(BASE.parent / "world" / "characters.md")

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

    user_msg = f"""请撰写《十日长安》第三十章《永恒囚徒》（终章）。

## 本章大纲
双线结局：轮回线（沈墨永恒轮回）+真实线（长安城破但无人）。这是全书终章，所有伏笔需在此回收。

## 批次协调简报（第30章）
入口状态：{ch30_brief.get('entry_state', '（无）')}
出口状态：{ch30_brief.get('exit_state', '（无）')}
必须揭示：{json.dumps(ch30_brief.get('must_reveal', []), ensure_ascii=False)}
禁止揭示：{json.dumps(ch30_brief.get('must_not_reveal', []), ensure_ascii=False)}
交接点：{ch30_brief.get('handoff', '（无）')}

## 前章（第29章）摘要
{ch29_summary}

## 第29章结尾正文（衔接用）
{ch29_story[-2000:]}

## 第28章摘要
{ch28_summary}

## 世界观参考
{world[:3000]}

## 角色参考
{characters[:2000]}

## 终章必须完成的内容
1. 始神的最终去向——带着所有灵魂共同编织的新梦沉入更深的底底，不再需要外部封印
2. 长安城失去天府之国属性后的具体变化——龙脉共生菌群消失，土地肥力回归普通水平，但城不因此衰败，因为城的根基从来不是神而是人
3. 所有主要角色的最终结局：玄宗与杨贵妃（马嵬坡的梦不再轮回）、李白（从笼子中解脱）、公孙大娘（第一代封印者的倒影消散）、高力士（守护结束）、更夫（最后一次敲梆子后嘴角烙印消失）
4. 沈墨与阿九的灵魂连接在失去封印功能后的新形态——不再是碎片绑定，而是两人自由选择维持的连接，虎口与掌心的刀疤淡化为普通疤痕
5. 第七块碎片"
