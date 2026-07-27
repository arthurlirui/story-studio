#!/usr/bin/env python3
"""修复终审6处问题：ch27x3 + ch28x1 + ch29x1 + ch30结尾"""
import asyncio, httpx, sys
from pathlib import Path
import yaml

settings = yaml.safe_load(open('/home/pz03-b-003-pcl/code/story-studio/config/settings.yaml'))
API_BASE = settings.get('llm_base_url', 'https://llmapi.pcl.ac.cn/v1')
API_KEY = settings.get('llm_api_key', '')
MODEL = settings.get('main_model', 'DeepSeek-V4-Pro')

BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/轮回怪谈/variants/01_十日长安/knowledge/story")
CH = BASE / "chapters"
SM = BASE / "summaries"

def rf(p):
    return Path(p).read_text('utf-8') if Path(p).exists() else ""

async def llm(client, msgs, mt=4096):
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

SYS = "你是一位资深网文作家，擅长志怪灵异题材。文风沉郁厚重，对话精炼。只输出正文，不要说明。"

async def fix27(client):
    print("📝 ch27...")
    txt = rf(CH/"chapter_027.md")[-4000:]
    s26, s28 = rf(SM/"chapter_026.md"), rf(SM/"chapter_028.md")
    msg = f"""《十日长安》第27章需插入3段文本修复跨章矛盾。

## 第27章末尾正文
{txt}

## 第26章摘要
{s26}

## 第28章摘要
{s28}

## 插入1：第七块碎片定义衔接
位置：沈墨伸手插入安禄山胸口之前
内容：明确第七块碎片不是一个人也不是一段关系，是两人通过连接共同构成的整体，缺任一人碎片就不完整。2-3句。

## 插入2：上一个沈墨终点内心独白
位置：安禄山说"上一个沈墨松手"之后
内容：沈墨内心独白——他理解上一个沈墨走到哪一步：摸到因果线边缘、看清完整规则、发现反噬同时摧毁两人。2-3句。

## 插入3：本轮沈墨与上一个的区分
位置：沈墨说"我不怕"之后
内容：区分——上一个沈墨怕的是阿九承受不住，本轮沈墨不怕是因为理解了阿九从来没有弱过。2句。

## 格式
每处输出：
【插入N】
位置：XXX之后
正文：（直接输出小说正文，对话用「」）

只输出这3组插入文本。"""
    r = await llm(client, [{"role":"system","content":SYS},{"role":"user","content":msg}], 2048)
    if r:
        with open(CH/"chapter_027.md","a",encoding='utf-8') as f:
            f.write("\n\n## 终审修订插入\n\n"+r+"\n")
        print(f"  ✅ ch27 +{len(r)}字")

async def fix28(client):
    print("📝 ch28...")
    txt = rf(CH/"chapter_028.md")[:3000:]
    s27 = rf(SM/"chapter_027.md")
    msg = f"""《十日长安》第28章需插入1段文本修复衔接问题。

## 第27章摘要
{s27}

## 第28章开头
{txt}

## 插入：双耳失聪感知替代说明
位置：第28章沈墨第一次需要感知声音之前
内容：沈墨双耳失聪后如何感知世界——通过虎口疤与阿九掌心的灵魂连接传递共振，共振替代声波，灵魂听力替代物理听力。3句。

## 格式
【插入】
位置：XXX之后
正文：（直接输出小说正文）"""
    r = await llm(client, [{"role":"system","content":SYS},{"role":"user","content":msg}], 1024)
    if r:
        with open(CH/"chapter_028.md","a",encoding='utf-8') as f:
            f.write("\n\n## 终审修订插入\n\n"+r+"\n")
        print(f"  ✅ ch28 +{len(r)}字")

async def fix29(client):
    print("📝 ch29...")
    txt = rf(CH/"chapter_029.md")[2000:5000:]
    s28 = rf(SM/"chapter_028.md")
    msg = f"""《十日长安》第29章需插入1句身份统一句。

## 第28章摘要
{s28}

## 第29章关键段落
{txt}

## 插入：阿九第零轮身份统一
位置：揭示第零轮女孩真相之后
内容：统一阿九的身份——她不是第零轮那个女孩，第零轮的女孩是另一个被冤的人。阿九是守墓人独孤信用女娲造人古法造的锚点，以李氏娘为原型。但阿九的灵魂连接里承载了第零轮女孩的最后一份愿。1-2句。

## 格式
【插入】
位置：XXX之后
正文：（直接输出小说正文，对话用「」）"""
    r = await llm(client, [{"role":"system","content":SYS},{"role":"user","content":msg}], 1024)
    if r:
        with open(CH/"chapter_029.md","a",encoding='utf-8') as f:
            f.write("\n\n## 终审修订插入\n\n"+r+"\n")
        print(f"  ✅ ch29 +{len(r)}字")

async def fix30(client):
    print("📝 ch30...")
    txt = rf(CH/"chapter_030.md")[-3000:]
    s29 = rf(SM/"chapter_029.md")
    msg = f"""《十日长安》第30章（终章）结尾需补写800-1000字。

## 第29章摘要
{s29}

## 第30章当前结尾
{txt}

## 需补写的内容
从"像天亮的声音。"之后继续，补写约800-1000字收束全书：
1. 阿九问"去哪儿？"——沈墨说"哪儿都不去。"
2. 两人坐在安仁坊废墟的井边，阳光照进来
3. 沈墨虎口的疤和阿九掌心的疤在阳光下只是普通旧疤
4. 更夫最后一次敲梆子后嘴角烙印消失
5. 长安城不会因此衰败——城的根基是人不是神
6. 始神带着所有灵魂共同编织的新梦沉入更深的底底，不再需要封印
7. 最后一句收束：不是宏大叙事，是日常的平静

## 要求
1. 对话用「」引号
2. 文风沉郁厚重但此刻平静
3. 不留续集暗示
4. 只输出补写的正文"""
    r = await llm(client, [{"role":"system","content":SYS},{"role":"user","content":msg}], 4096)
    if r:
        with open(CH/"chapter_030.md","a",encoding='utf-8') as f:
            f.write("\n\n"+r+"\n")
        print(f"  ✅ ch30 +{len(r)}字")

async def main():
    async with httpx.AsyncClient() as client:
        # Run all 4 fixes in parallel
        await asyncio.gather(
            fix27(client), fix28(client), fix29(client), fix30(client)
        )
    print("🎉 全部修订完成")

if __name__ == "__main__":
    asyncio.run(main())
