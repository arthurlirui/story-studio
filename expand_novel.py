#!/usr/bin/env python3
"""
玉璧之战 扩写脚本 — 从 ~18k 字扩展到 ~50k 字
每章从 ~2k 扩展到 ~5-6k 字，增加细节刻画和心理活动
"""
import os
import sys
from pathlib import Path

WORK_DIR = Path("/data/openclaw/workspace/story-studio/玉璧之战")
CHAPTERS_DIR = WORK_DIR
EXPANDED_DIR = WORK_DIR / "expanded"
EXPANDED_DIR.mkdir(parents=True, exist_ok=True)

# 扩写要求
EXPANSION_PROMPT_TEMPLATE = """请将以下章节扩写，要求：

## 字数目标
从当前约 2000 字扩展到 5000-6000 字。

## 扩写重点
1. **细节刻画**：丰富环境描写（感官细节——视觉、听觉、嗅觉、触觉、温度），增加战场细节
2. **心理活动**：深入角色的内心世界——恐惧、犹豫、决心、回忆、幻觉
3. **对话扩展**：增加角色之间的对话，展现性格和关系
4. **动作描写**：战斗场面更加细致，每一个动作都要有力度和画面感
5. **节奏控制**：保持原有的紧张→舒缓→高潮的节奏，不要破坏原有结构

## 扩写原则
- 保留原文所有情节和关键对话
- 在原文基础上"填充"而非"改写"
- 展示不要告诉 (Show, Don't Tell)
- 保持第三人称有限视角
- 保持原文的文学风格和基调

## 原文
{chapter_content}

---

请输出扩写后的完整章节（5000-6000字），以"# 第X章：标题"开头。"""


def main():
    print("=" * 60)
    print("玉璧之战 扩写任务")
    print("=" * 60)

    # List current chapters
    chapters = sorted([f for f in os.listdir(CHAPTERS_DIR) if f.startswith("04_第") and f.endswith(".md")])
    print(f"找到 {len(chapters)} 个章节")

    for ch_file in chapters:
        ch_path = CHAPTERS_DIR / ch_file
        content = ch_path.read_text(encoding="utf-8")
        char_count = len(content)
        print(f"  {ch_file}: {char_count} 字")

    # Save expansion prompts for each chapter
    prompts_dir = EXPANDED_DIR / "prompts"
    prompts_dir.mkdir(exist_ok=True)

    for ch_file in chapters:
        ch_path = CHAPTERS_DIR / ch_file
        content = ch_path.read_text(encoding="utf-8")
        prompt = EXPANSION_PROMPT_TEMPLATE.format(chapter_content=content)
        prompt_path = prompts_dir / f"{ch_file.replace('.md', '_prompt.md')}"
        prompt_path.write_text(prompt, encoding="utf-8")
        print(f"  生成扩写提示: {prompt_path.name}")

    # Write a status file
    status = {
        "total_chapters": len(chapters),
        "expanded_chapters": 0,
        "target_words_per_chapter": 5500,
        "total_target_words": len(chapters) * 5500,
    }
    import json
    (EXPANDED_DIR / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2))

    print(f"\n扩写提示已生成到: {prompts_dir}")
    print(f"状态文件: {EXPANDED_DIR / 'status.json'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
