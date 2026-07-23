#!/usr/bin/env python3
"""导出最终版：全本txt + 简介 + cover提示词"""
import asyncio, httpx, re, sys, shutil
from pathlib import Path

API_BASE = "https://llmapi.pcl.ac.cn/v1"
API_KEY = "sk-dLcQBdtUNpw5vxrSP8HjlXfJGb8nP8uYlpSMpfKKTD8QfbbS"
MODEL = "DeepSeek-V4-Pro"

BASE = Path("/home/pz03-b-003-pcl/code/story-studio/series/轮回怪谈/variants/01_十日长安")
CH = BASE / "knowledge" / "story" / "chapters"
OUT = BASE / "output"
OUT.mkdir(parents=True, exist_ok=True)

def extract_pure_story(text):
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# 第"):
            result.append(stripped)
            continue
        if stripped.startswith("✅"):
            continue
        if stripped.startswith("**") and re.match(r"^\*\*\d+\.", stripped):
            continue
        if stripped.startswith("# 编辑") or stripped.startswith("## 终审"):
            continue
        if stripped.startswith("本章以") and not stripped.startswith(">"):
            continue
        if stripped in ("以下逐段确认。",):
            continue
        if re.match(r"^文风以", stripped):
            continue
        result.append(line)
    text = "\n".join(result)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()

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

async def main():
    print("📚 合并30章正文...")
    chapters = sorted(CH.glob("chapter_*.md"), key=lambda p: int(re.search(r"(\d+)", p.name).group()))
    print(f"  找到 {len(chapters)} 章")
    
    full_text = ""
    total_chars = 0
    for ch in chapters:
        raw = ch.read_text("utf-8")
        cleaned = extract_pure_story(raw)
        full_text += cleaned + "\n\n---\n\n"
        total_chars += len(cleaned)
        print(f"  {ch.name}: {len(cleaned)} 字")
    
    print(f"\n  全书共 {total_chars} 字")
    
    txt_path = OUT / "十日长安.txt"
    txt_path.write_text(full_text.replace("---\n\n", "\n\n"), encoding="utf-8")
    print(f"  ✅ 全本TXT: {txt_path} ({txt_path.stat().st_size // 1024}KB)")
    
    async with httpx.AsyncClient() as client:
        outline = (BASE / "knowledge" / "story" / "outline.md").read_text("utf-8")[:3000]
        sample = chapters[0].read_text("utf-8")[:2000]
        ending = chapters[-1].read_text("utf-8")[:2000]
        
        synopsis_msg = f"""请为小说《十日长安》写一段简介（300-500字）。

## 大纲
{outline}

## 开头节选
{sample}

## 结尾节选
{ending}

## 要求
1. 简介不要剧透核心反转（第零轮真相、始神真名、替代锚点）
2. 点明故事基调：志怪灵异 + 唐代长安 + 轮回
3. 暗示核心冲突：十日轮回、碎片收集、封印将破
4. 吸引读者但不夸大
5. 只输出简介正文，不要标题"""

        cover_msg = f"""请为小说《十日长安》生成一张封面图的AI绘画提示词。

## 故事背景
{outline[:1500]}

## 封面要素
- 风格：中式水墨/工笔混合，暗色调
- 场景：长安城俯瞰，夜色，北斗七星悬于城上
- 人物：两个剪影（一男一女）站在城墙边缘，面对星空
- 氛围：神秘、沉重、带一丝希望
- 细节：城下有微弱的金色光芒从地面裂缝中渗出

## 要求
输出一段英文的AI绘画提示词（prompt），适合Midjourney或Stable Diffusion使用。
包含风格、构图、光影、色彩、细节描述。
只输出英文prompt，不要中文说明。"""

        print("\n📝 生成简介和封面提示词...")
        synopsis, cover = await asyncio.gather(
            llm(client, [{"role":"system","content":"你是一位资深网文编辑。"},{"role":"user","content":synopsis_msg}], 1024),
            llm(client, [{"role":"system","content":"You are an expert at crafting AI art prompts."},{"role":"user","content":cover_msg}], 1024)
        )
    
    if synopsis:
        (OUT / "story_synopsis.txt").write_text(synopsis, encoding="utf-8")
        print(f"  ✅ 简介: {OUT / 'story_synopsis.txt'}")
    if cover:
        (OUT / "cover_prompt.txt").write_text(cover, encoding="utf-8")
        print(f"  ✅ 封面提示词: {OUT / 'cover_prompt.txt'}")
    
    home_novel = Path("/home/pz03-b-003-pcl/小说")
    home_novel.mkdir(exist_ok=True)
    shutil.copy2(txt_path, home_novel / "十日长安.txt")
    if synopsis:
        shutil.copy2(OUT / "story_synopsis.txt", home_novel / "十日长安_简介.txt")
    if cover:
        shutil.copy2(OUT / "cover_prompt.txt", home_novel / "十日长安_封面提示词.txt")
    print(f"\n  ✅ 已复制到 ~/小说/")

if __name__ == "__main__":
    asyncio.run(main())
