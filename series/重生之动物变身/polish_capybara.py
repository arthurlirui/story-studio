#!/usr/bin/env python3
"""
网文风格润色脚本 — 将卡皮巴拉小说润色为轻快、幽默、可爱的网文风格。

使用火山引擎API，逐章润色，支持并发。
"""
import asyncio
import httpx
import os
import re
import sys
import json
from pathlib import Path

# Config
API_BASE = "https://ark.cn-beijing.volces.com/api/coding/v3"
API_KEY = "ark-cbb53828-980b-4d51-89c3-215947aa79f1-62bef"
MODEL = "ark-code-latest"
INPUT_DIR = "/tmp/capybara_chapters"
OUTPUT_DIR = "/data/openclaw/workspace/story-studio/series/重生之动物变身/output"
BOOK_TITLE = "重生为卡皮巴拉后，我被顶流女星当枕头了"
CONCURRENCY = 3  # 并发章节数
MAX_RETRIES = 5

SYSTEM_PROMPT = """你是一位专业的网文编辑，擅长将小说文字润色为轻快、幽默、可爱的网文风格。

## 润色要求

### 风格定位
- **轻快**：句子短、节奏快、读起来像在刷短视频，拒绝长段堆砌
- **幽默**：内心吐槽要犀利又好笑，多用自嘲、反转、意外感
- **可爱**：卡皮巴拉的萌感要拉满——面瘫脸配燥动心的反差要更突出

### 具体手法
1. **内心独白升级**：把"——"开头的内心吐槽写得更弹幕化、更有网感
   - 原："——我连遗言都是乱码，这很程序员。"
   - 润色后："——我连遗言都是乱码。程序员的一生，从Hello World到asdfghjkl，闭环了属于是。"
   
2. **动物萌感强化**：多写卡皮巴拉的呆萌动作细节——眯眼、泡澡、发呆、慢半拍
   - 水豚的佛系感要用具体动作展现，不要只说"淡定"
   
3. **对话更口语化**：人物对话要像真人说话，不要像念台词
   - 多用"啊""哎""嘛""嘿"等语气词
   - 允许 incomplete sentences、省略主语
   
4. **节奏感**：短句和长句交替，关键笑点单独成行，制造"抖包袱"的节奏
   - 笑点前可以稍微铺垫，笑点处一个短句炸出来
   
5. **适度玩梗**：可以加入当下网络流行语，但不滥用
   - "属于是""谁懂啊""离谱给离谱开门""CPU烧了"等
   
6. **暧昧场景**：保持擦边但可爱的基调，用卡皮巴拉的动物视角让暧昧更天然
   - 不改原有情节，只让描写更萌更甜

### 禁止事项
- ❌ 不要改变任何故事情节、角色关系、核心事件
- ❌ 不要增加或删除任何角色
- ❌ 不要改变章节标题
- ❌ 不要增加任何标注、注释、说明——只输出润色后的正文
- ❌ 不要输出思考过程
- ✅ 保留所有"——"开头的内心独白格式
- ✅ 保留章节标题（第X章 标题）
- ✅ 保留所有空行格式（段落间空一行，章节间空两行）

### 输出格式
直接输出润色后的章节全文，格式与输入一致。不要输出任何额外内容。"""


async def polish_chapter(client: httpx.AsyncClient, chapter_num: int, content: str, semaphore: asyncio.Semaphore) -> tuple[int, str]:
    """Polish a single chapter."""
    async with semaphore:
        print(f"  [Ch{chapter_num}] 开始润色 ({len(content)} 字)...")
        
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"请润色以下章节，保持格式不变，只优化文字风格：\n\n{content}"}
            ],
            "temperature": 0.85,
            "max_tokens": 16000,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(
                    f"{API_BASE}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=300.0,
                )
                
                if resp.status_code == 429:
                    delay = min(5 * (2 ** attempt), 60)
                    print(f"  [Ch{chapter_num}] 429限流, {delay:.0f}s后重试 ({attempt+1}/{MAX_RETRIES})")
                    await asyncio.sleep(delay)
                    continue
                
                resp.raise_for_status()
                data = resp.json()
                result = data["choices"][0]["message"]["content"].strip()
                
                # Clean up any potential thinking markers
                result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
                result = re.sub(r'^```(?:text|markdown)?\s*\n', '', result)
                result = re.sub(r'\n```\s*$', '', result)
                
                print(f"  [Ch{chapter_num}] ✅ 完成 ({len(result)} 字)")
                return chapter_num, result
                
            except Exception as e:
                print(f"  [Ch{chapter_num}] ❌ 错误: {e} ({attempt+1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    print(f"  [Ch{chapter_num}] ❌ 跳过，使用原文")
                    return chapter_num, content


async def main():
    # Read all chapter files
    chapter_files = sorted(Path(INPUT_DIR).glob("ch*.txt"))
    chapters = []
    for cf in chapter_files:
        num = int(cf.stem[2:])
        content = cf.read_text(encoding="utf-8")
        chapters.append((num, content))
    
    print(f"读取 {len(chapters)} 章待润色")
    print(f"并发数: {CONCURRENCY}")
    print()
    
    # Polish all chapters concurrently
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async with httpx.AsyncClient() as client:
        tasks = [polish_chapter(client, num, content, semaphore) for num, content in chapters]
        results = await asyncio.gather(*tasks)
    
    # Sort results by chapter number
    results.sort(key=lambda x: x[0])
    
    # Combine into final text
    print("\n合并章节...")
    parts = [BOOK_TITLE, "", ""]
    for num, content in results:
        parts.append(content)
        parts.append("")
        parts.append("")
    
    final_text = "\n".join(parts).rstrip() + "\n"
    
    # Save
    output_path = os.path.join(OUTPUT_DIR, "卡皮巴拉_番茄小说版.txt")
    
    # Backup original
    backup_path = os.path.join(OUTPUT_DIR, "卡皮巴拉_番茄小说版_原版.txt")
    if not os.path.exists(backup_path):
        import shutil
        shutil.copy2(output_path, backup_path)
        print(f"原版已备份: {backup_path}")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)
    
    print(f"\n✅ 润色完成!")
    print(f"   输出: {output_path}")
    print(f"   字数: {len(final_text)}")
    
    # Also regenerate combined file
    combined_path = os.path.join(OUTPUT_DIR, "重生之动物变身_合集_番茄小说版.txt")
    if os.path.exists(combined_path):
        print("\n更新合集文件...")


if __name__ == "__main__":
    asyncio.run(main())
