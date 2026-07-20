#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说格式清洗：把 series/重生穿越/story 下 11 部小说的 Markdown 章节
清洗成可直接粘贴到番茄小说的纯文本 txt。

清洗规则（保正文，去排版）：
- 去 Markdown 标题符 #，标题转「第X章 标题」独立成行
- 去水平分隔线 --- *** ___（转为场景空行）
- 去粗体 **x** / 斜体 *x* 的星号（保留文字）
- 去行首引用符 >（保留引用内容文字）
- 去无序列表符号 - / * / +（行首）
- 去行内代码/反引号 `
- 英文直引号 " → 中文成对引号 “ ”
- 正文箭头 → 转顿号/逗号（表“导致/对应”语境）
- 规范空行：段落之间最多 1 个空行
- 行首行尾空白清理
- 保留剧情中的数学/工程符号（= × ≠ Δ 等，属正文内容，番茄可正常显示）

用法: python3 tomato_clean.py
输出: series/重生穿越/tomato_txt/<NN_书名>.txt   （整本一个 txt，方便直接粘贴）
"""
from __future__ import annotations
import os
import re
import glob

BASE = "/data/openclaw/workspace/story-studio/series/重生穿越/story"
OUT = "/data/openclaw/workspace/story-studio/series/重生穿越/tomato_txt"

# 每部书的源文件选择：
#   final -> 用 final.md（整本合订）
#   chapters -> 用分章文件（按文件名排序），并指定 glob 与排除
BOOK_PLAN = {
    "01_铁与火之歌": {"mode": "final"},
    "02_崖山之后": {"mode": "final"},
    "03_崇祯十五年": {"mode": "chapters", "glob": "第*.md"},
    "04_长安十二行": {"mode": "chapters", "glob": "chapter_*.md"},
    # 05 有两套版本：用「第X章」版（完整 8 章；ch 版缺第4章）
    "05_从长城到未央宫": {"mode": "chapters", "glob": "第*.md"},
    "06_赤脚医生": {"mode": "chapters", "glob": "第*.md"},
    "07_洪武的阴影": {"mode": "chapters", "glob": "第*.md"},  # 有 final 但也有分章，用分章更稳
    "08_靖康之变": {"mode": "chapters", "glob": "ch*.md"},
    # 09 的 final 只含 1 章（不全），用分章
    "09_海疆": {"mode": "chapters", "glob": "chapter_*.md"},
    "10_十亩之间": {"mode": "chapters", "glob": "chapter_*.md"},
    # 11 潮汐 为空目录，跳过
}

# 中文数字，用于章节序号排序辅助
CN_NUM = {c: i for i, c in enumerate("一二三四五六七八九十", 1)}


def chinese_chapter_key(path: str):
    """从文件名/首行提取章节序号用于排序。"""
    name = os.path.basename(path)
    # 优先文件名里的阿拉伯数字
    m = re.search(r'(?:chapter_|ch|第)(\d+)', name)
    if m:
        return int(m.group(1))
    # 中文数字
    m = re.search(r'第([一二三四五六七八九十]+)章', name)
    if m:
        s = m.group(1)
        if s == "十":
            return 10
        if s.startswith("十"):
            return 10 + CN_NUM.get(s[1:], 0)
        if s.endswith("十"):
            return CN_NUM.get(s[0], 0) * 10
        if "十" in s:
            a, b = s.split("十")
            return CN_NUM.get(a, 0) * 10 + CN_NUM.get(b, 0)
        return CN_NUM.get(s, 0)
    return 999


def fix_english_quotes(text: str) -> str:
    """英文直引号成对转中文引号。"""
    out = []
    open_q = True
    for ch in text:
        if ch == '"':
            out.append('\u201c' if open_q else '\u201d')
            open_q = not open_q
        else:
            out.append(ch)
    return ''.join(out)


def clean_title(line: str) -> str:
    t = re.sub(r'^#{1,6}\s*', '', line).strip()
    # 「第1章：夜袭」/「第一章 玉璧」统一为「第X章 标题」（冒号转空格）
    t = t.replace('\uff1a', ' ').replace(':', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def clean_body(text: str) -> str:
    lines = text.split('\n')
    out_lines = []
    for ln in lines:
        s = ln.rstrip()
        # 水平分隔线 -> 空行（场景分隔）
        if re.match(r'^\s*[-*_]{3,}\s*$', s):
            out_lines.append('')
            continue
        # 正文内的 Markdown 标题符（## 一、### 场景 等场景/小节标记）-> 去符号保留文字
        if re.match(r'^\s*#{1,6}\s', s):
            s = re.sub(r'^\s*#{1,6}\s*', '', s)
            s = s.replace('\uff1a', ' ').replace(':', ' ').strip()
            out_lines.append(s)
            continue
        # 行首引用符 >（可多层）
        s = re.sub(r'^\s*>+\s?', '', s)
        # 行首无序列表符号 - * + （后跟空格）
        s = re.sub(r'^\s*[-*+]\s+', '', s)
        # 去粗体/斜体星号（保留文字）
        s = re.sub(r'\*\*([^*]+)\*\*', r'\1', s)
        s = re.sub(r'\*([^*]+)\*', r'\1', s)
        # 残留成对/零散星号、下划线强调
        s = s.replace('**', '').replace('*', '')
        # 行内反引号
        s = s.replace('`', '')
        out_lines.append(s.strip())
    text = '\n'.join(out_lines)

    # 正文箭头 → 转“，”（表导致/对应/路线）
    text = text.replace(' → ', '，').replace('→', '，')

    # 引号规范
    text = fix_english_quotes(text)

    # 规范空行：3+ 连续换行 -> 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def convert_chapter(raw: str):
    """输入一段（含 # 标题）的 Markdown，返回 (标题, 正文)。"""
    lines = raw.split('\n')
    title = ''
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.strip():
            if re.match(r'^#{1,6}\s', ln):
                title = clean_title(ln)
                body_start = i + 1
            else:
                body_start = i
            break
    body = '\n'.join(lines[body_start:])
    return title, clean_body(body)


def split_final_into_chapters(text: str):
    """final.md 用一级标题 # 切分成多章。"""
    # 在每个 '# ' 前切
    parts = re.split(r'(?m)^(?=#\s)', text)
    return [p for p in parts if p.strip()]


def process_book(folder: str, plan: dict):
    src_dir = os.path.join(BASE, folder)
    chapters = []  # list of (title, body)

    if plan["mode"] == "final":
        raw = open(os.path.join(src_dir, "final.md"), encoding="utf-8").read()
        for seg in split_final_into_chapters(raw):
            t, b = convert_chapter(seg)
            if b:
                chapters.append((t, b))
    else:
        files = glob.glob(os.path.join(src_dir, plan["glob"]))
        files = [f for f in files if os.path.basename(f) not in ("final.md", "_STORY_BIBLE.md")]
        files.sort(key=chinese_chapter_key)
        for f in files:
            raw = open(f, encoding="utf-8").read()
            t, b = convert_chapter(raw)
            if b:
                chapters.append((t, b))
    return chapters


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for folder, plan in BOOK_PLAN.items():
        src_dir = os.path.join(BASE, folder)
        if not os.path.isdir(src_dir):
            continue
        chapters = process_book(folder, plan)
        if not chapters:
            print(f"  跳过 {folder}（无内容）")
            continue
        # 书名 = 去掉编号前缀
        book_title = re.sub(r'^\d+_', '', folder)
        blocks = []
        for idx, (title, body) in enumerate(chapters, 1):
            if not title:
                title = f"第{idx}章"
            blocks.append(f"{title}\n\n{body}")
        full = f"{book_title}\n\n" + "\n\n\n".join(blocks) + "\n"
        # 最终再规范一次空行（章节之间保留 2 空行）
        full = re.sub(r'\n{4,}', '\n\n\n', full)
        out_path = os.path.join(OUT, f"{folder}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full)
        chars = len(full)
        summary.append((folder, len(chapters), chars))
        print(f"  ✓ {folder}: {len(chapters)} 章, {chars} 字 → {os.path.basename(out_path)}")

    print(f"\n完成 {len(summary)} 部 → {OUT}")


if __name__ == "__main__":
    main()
