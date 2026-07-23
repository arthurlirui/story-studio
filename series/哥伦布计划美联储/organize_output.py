#!/usr/bin/env python3
"""
整理《杰基尔岛密谋》小说文件，输出到 output 目录
- 按书名/卷名/章节序号_章节名.md 结构
- 同时生成 txt 文件（去除 markdown 特殊字符，可直接粘贴到番茄小说）
"""

import os
import re
import shutil

SOURCE = "/home/openclaw/.openclaw/workspace/story-studio/series/哥伦布计划美联储/variants/02_杰基尔岛密谋"
OUTPUT = "/data/openclaw/workspace/story-studio/series/哥伦布计划美联储/output"

BOOK_NAME = "杰基尔岛密谋"

# 卷结构: (卷目录名, 起始章, 结束章)
VOLUMES = [
    ("第一卷_猎鸭邀请", 1, 12),
    ("第二卷_九天密室", 13, 24),
    ("第三卷_政治炼金术", 25, 36),
    ("第四卷_圣诞夜法案", 37, 48),
]

NOVEL_DIR = os.path.join(SOURCE, "novel")

def get_chapter_files():
    """获取 novel/ 目录下所有章节文件，返回 {章节号: 文件路径}"""
    pattern = re.compile(r'^ch(\d+)_(.+)\.md$')
    chapters = {}
    if not os.path.isdir(NOVEL_DIR):
        return chapters
    for fname in os.listdir(NOVEL_DIR):
        m = pattern.match(fname)
        if m:
            ch_num = int(m.group(1))
            ch_name = m.group(2)
            chapters[ch_num] = (os.path.join(NOVEL_DIR, fname), ch_name)
    return chapters

def get_volume(ch_num):
    """根据章节号返回卷名"""
    for vol_name, start, end in VOLUMES:
        if start <= ch_num <= end:
            return vol_name
    return None

def md_to_txt(md_text):
    """将 markdown 转换为纯文本，适合番茄小说"""
    text = md_text
    
    # 去掉 markdown 标题标记 (#, ##, ###)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # 去掉引用块标记 (>)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # 去掉加粗/斜体
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.+?)_{1,3}', r'\1', text)
    
    # 去掉行内代码
    text = re.sub(r'`(.+?)`', r'\1', text)
    
    # 去掉代码块
    text = re.sub(r'```[\s\S]*?```', '', text)
    
    # 去掉链接，保留文本
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # 去掉图片
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)
    
    # 去掉水平分割线 (---, ***, ___)
    text = re.sub(r'^[\-\*_]{3,}$', '', text, flags=re.MULTILINE)
    
    # 去掉列表标记 (-, *, +, 1.)
    text = re.sub(r'^[\s]*[-\*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # 去掉表格（整行去掉含 | 的行）
    text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*[\-\:]+[\s]*$', '', text, flags=re.MULTILINE)
    
    # 去掉 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    
    # 清理多余空行：连续3个以上换行变2个
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 去掉首尾空白
    text = text.strip()
    
    return text

def format_chapter_filename(ch_num, ch_name):
    """格式化章节文件名: 第01章_摩根的审判"""
    return f"第{ch_num:02d}章_{ch_name}"

def main():
    chapters = get_chapter_files()
    
    if not chapters:
        print("❌ 未找到章节文件")
        return
    
    print(f"📖 找到 {len(chapters)} 个章节文件 (ch01-ch{max(chapters):02d})")
    
    # 创建输出目录
    book_dir = os.path.join(OUTPUT, BOOK_NAME)
    
    # 清空旧的输出目录（如果存在）
    if os.path.exists(book_dir):
        shutil.rmtree(book_dir)
    
    os.makedirs(book_dir, exist_ok=True)
    
    md_count = 0
    txt_count = 0
    missing_chapters = []
    
    for vol_name, start, end in VOLUMES:
        vol_dir = os.path.join(book_dir, vol_name)
        os.makedirs(vol_dir, exist_ok=True)
        
        for ch_num in range(start, end + 1):
            if ch_num not in chapters:
                missing_chapters.append(ch_num)
                print(f"  ⚠️  第{ch_num:02d}章 无正文文件，跳过")
                continue
            
            src_path, ch_name = chapters[ch_num]
            base_name = format_chapter_filename(ch_num, ch_name)
            
            # 读取 md 内容
            with open(src_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # 写入 md 文件
            md_path = os.path.join(vol_dir, f"{base_name}.md")
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            md_count += 1
            
            # 转换并写入 txt 文件
            txt_content = md_to_txt(md_content)
            txt_path = os.path.join(vol_dir, f"{base_name}.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(txt_content)
            txt_count += 1
            
            print(f"  ✅ {vol_name}/{base_name}.md + .txt")
    
    print(f"\n📊 统计:")
    print(f"   MD 文件: {md_count}")
    print(f"   TXT 文件: {txt_count}")
    if missing_chapters:
        print(f"   ⚠️  缺少正文章节: 第{', '.join(f'{c:02d}' for c in missing_chapters)}章（仅有大纲，未生成正文）")
    print(f"   📁 输出目录: {book_dir}")

if __name__ == '__main__':
    main()
