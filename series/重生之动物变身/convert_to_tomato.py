#!/usr/bin/env python3
"""
深度清理《重生之动物变身》系列小说，输出番茄小说可直接粘贴的txt。

处理规则：
1. 去除所有markdown标记
2. 去除结构性标记文本（爽点/笑点/暧昧场景/章末统计/章末悬念/下一章预告/字数统计等）
3. 金毛final.md去重：逐章检查，去除重复段落
4. 规范化空行
5. 每部小说顶部加书名，章节间空2行
"""

import re
import os
import glob

BASE = "/data/openclaw/workspace/story-studio/series/重生之动物变身/novels"
OUT = "/data/openclaw/workspace/story-studio/series/重生之动物变身/output"

NOVELS = [
    {
        "dir": "01_卡皮巴拉",
        "title": "重生为卡皮巴拉后，我被顶流女星当枕头了",
        "source": "final.md",
    },
    {
        "dir": "02_金毛",
        "title": "变成金毛后，我给女总裁当贴身保镖天天舔",
        "source": "chapters",  # Use chapters to avoid final.md duplication
    },
    {
        "dir": "04_仓鼠",
        "title": "变成仓鼠后，我被美女主播捧在手心直播",
        "source": "final.md",
    },
    {
        "dir": "05_垂耳兔",
        "title": "重生为垂耳兔后，国际超模把我当围脖天天戴",
        "source": "chapters",
    },
]

# Structural marker patterns to remove
STRUCTURAL_PATTERNS = [
    # Chapter-end statistics
    r'^章末统计[：:].*',
    r'^章末统计.*',
    # Chapter-end cliffhanger notes (but NOT "章末悬念" as a section header in subheaders - those are already removed)
    r'^章末悬念[：:].*',
    r'^章末悬念.*',
    # Standalone cliffhanger markers
    r'^悬念[：:].*',
    r'^悬念.*',
    # Next chapter previews
    r'^下一章预告[：:].*',
    r'^下一章预告.*',
    # Word count markers
    r'^字数[：:].*',
    r'^字数.*约.*字',
    r'^纯汉字数.*',
    r'^含标点.*',
    r'^-?\s*总字数.*',
    # Joy/laugh/ambiguity point markers
    r'^爽点[：:].*',
    r'^笑点[：:].*',
    r'^暧昧场景[：:].*',
    r'^高潮[：:].*',
    # Character profile / outline markers
    r'^角色档案.*',
    r'^本书设定.*',
]


def is_structural_marker(line):
    """Check if a line is a structural marker that should be removed."""
    stripped = line.strip()
    for pattern in STRUCTURAL_PATTERNS:
        if re.match(pattern, stripped):
            return True
    # Also check for lines starting with 爽点/笑点 that use ①②③ format
    if re.match(r'^(爽点|笑点|暧昧场景|高潮)[：:]', stripped):
        return True
    # Check for "字数：约XXXX字"
    if re.match(r'^字数[：:].*字\s*$', stripped):
        return True
    return False


def clean_markdown(line):
    """Remove inline markdown formatting from a line, keeping text content."""
    line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
    line = re.sub(r'\*([^*\n]+?)\*', r'\1', line)
    line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
    return line


def is_image_line(line):
    return line.strip().startswith("![") or bool(re.match(r'^\s*!\[', line))


def is_horizontal_rule(line):
    s = line.strip()
    return bool(re.match(r'^-{3,}\s*$', s)) or bool(re.match(r'^\*{3,}\s*$', s))


def is_chapter_header(line):
    stripped = line.strip()
    if not stripped.startswith("#"):
        return False
    return bool(re.match(r'^#+\s*第\d+章', stripped))


def is_subheader(line):
    stripped = line.strip()
    return stripped.startswith("## ") or stripped.startswith("### ")


def clean_chapter_title(line):
    stripped = line.strip()
    stripped = re.sub(r'^#+\s*', '', stripped)
    stripped = re.sub(r'^(第.+?章)[：:]\s*', r'\1 ', stripped)
    return stripped


def process_final_md(filepath, novel_title):
    """Process a final.md file into clean txt, with global dedup."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split("\n")
    result = []
    first_chapter_found = False
    seen_lines = set()  # Track lines >30 chars to dedup
    
    for line in lines:
        # Detect chapter headers
        if is_chapter_header(line):
            if not first_chapter_found:
                first_chapter_found = True
            title = clean_chapter_title(line)
            if result:
                while result and result[-1].strip() == "":
                    result.pop()
                result.append("")
                result.append("")
            result.append(title)
            result.append("")
            continue
        
        # Skip everything before first chapter
        if not first_chapter_found:
            continue
        
        # Skip subheaders
        if is_subheader(line):
            continue
        
        # Skip image lines
        if is_image_line(line):
            continue
        
        # Skip horizontal rules
        if is_horizontal_rule(line):
            continue
        
        # Skip structural markers
        if is_structural_marker(line):
            continue
        
        # Handle blockquote lines
        stripped = line.strip()
        if stripped == ">":
            continue
        if stripped.startswith(">"):
            content_after_quote = stripped[1:].strip()
            if is_structural_marker(content_after_quote):
                continue
            if re.match(r'^下一章预告', content_after_quote):
                continue
            line = content_after_quote
            if not line.strip():
                continue
        
        # Clean markdown
        cleaned = clean_markdown(line)
        
        if is_structural_marker(cleaned):
            continue
        
        # Normalize blank lines
        if cleaned.strip() == "":
            if result and result[-1].strip() == "":
                continue
            result.append("")
        else:
            # Global dedup: skip lines >30 chars already seen
            line_stripped = cleaned.strip()
            if len(line_stripped) > 30 and line_stripped in seen_lines:
                continue
            if len(line_stripped) > 30:
                seen_lines.add(line_stripped)
            result.append(cleaned.rstrip())
    
    # Remove trailing blank lines
    while result and result[-1].strip() == "":
        result.pop()
    
    # Remove trailing metadata (lines starting with - that look like book info)
    while result and (re.match(r'^-\s*(书名|总章节|核心|结局|暧昧|梗|字数)', result[-1].strip() or '') or re.match(r'^[（(].*[）)]\s*$', result[-1].strip() or '')):
        result.pop()
        # Also remove any blank lines before metadata
        while result and result[-1].strip() == "":
            result.pop()
    
    text = novel_title + "\n\n\n" + "\n".join(result) + "\n"
    return text


def deduplicate_paragraphs(lines):
    """Remove consecutive duplicate paragraph blocks."""
    if not lines:
        return lines
    
    result = []
    i = 0
    while i < len(lines):
        # Collect current paragraph block (non-empty lines until blank or end)
        current_block = []
        while i < len(lines) and lines[i].strip() != "":
            current_block.append(lines[i])
            i += 1
        
        # Check if this block is identical to the last added block
        is_duplicate = False
        if len(result) >= len(current_block) and len(current_block) > 0:
            # Compare with the last block in result
            last_block = result[-len(current_block):]
            # Make sure we're comparing a complete block (preceded by blank line)
            if len(result) > len(current_block) and result[-(len(current_block)+1)].strip() == "":
                if last_block == current_block:
                    is_duplicate = True
        
        if not is_duplicate:
            result.extend(current_block)
        
        # Add the blank line separator
        if i < len(lines) and lines[i].strip() == "":
            if result and result[-1].strip() != "":
                result.append("")
            i += 1
    
    return result


def process_chapters_dir(chapters_dir, novel_title):
    """Process individual chapter files into clean txt, with cross-chapter dedup."""
    chapter_files = sorted(glob.glob(os.path.join(chapters_dir, "*.md")))
    
    result = []
    seen_lines = set()  # Track lines >30 chars to dedup across chapters
    
    for cf in chapter_files:
        with open(cf, "r", encoding="utf-8") as f:
            content = f.read()
        
        lines = content.split("\n")
        chapter_started = False
        
        for line in lines:
            if is_chapter_header(line):
                chapter_started = True
                title = clean_chapter_title(line)
                if result:
                    while result and result[-1].strip() == "":
                        result.pop()
                    result.append("")
                    result.append("")
                result.append(title)
                result.append("")
                continue
            
            if not chapter_started:
                continue
            
            if is_subheader(line):
                continue
            
            if is_image_line(line):
                continue
            
            if is_horizontal_rule(line):
                continue
            
            if is_structural_marker(line):
                continue
            
            stripped = line.strip()
            if stripped == ">":
                continue
            if stripped.startswith(">"):
                content_after_quote = stripped[1:].strip()
                if is_structural_marker(content_after_quote):
                    continue
                if re.match(r'^下一章预告', content_after_quote):
                    continue
                line = content_after_quote
                if not line.strip():
                    continue
            
            cleaned = clean_markdown(line)
            
            if is_structural_marker(cleaned):
                continue
            
            if cleaned.strip() == "":
                if result and result[-1].strip() == "":
                    continue
                result.append("")
            else:
                # Cross-chapter dedup: skip lines >30 chars already seen
                line_stripped = cleaned.strip()
                if len(line_stripped) > 30 and line_stripped in seen_lines:
                    continue
                if len(line_stripped) > 30:
                    seen_lines.add(line_stripped)
                result.append(cleaned.rstrip())
    
    while result and result[-1].strip() == "":
        result.pop()
    
    # Remove trailing metadata
    while result and (re.match(r'^-\s*(书名|总章节|核心|结局|暧昧|梗|字数)', result[-1].strip() or '') or re.match(r'^[（(].*[）)]\s*$', result[-1].strip() or '')):
        result.pop()
        while result and result[-1].strip() == "":
            result.pop()
    
    # Also remove consecutive duplicate blocks (redundant but safe)
    result = deduplicate_paragraphs(result)
    
    text = novel_title + "\n\n\n" + "\n".join(result) + "\n"
    return text


def main():
    os.makedirs(OUT, exist_ok=True)
    
    for novel in NOVELS:
        novel_dir = os.path.join(BASE, novel["dir"])
        title = novel["title"]
        
        print(f"处理: {novel['dir']} -> {title}")
        
        if novel["source"] == "final.md":
            filepath = os.path.join(novel_dir, "final.md")
            if not os.path.exists(filepath):
                print(f"  跳过: {filepath} 不存在")
                continue
            text = process_final_md(filepath, title)
        else:
            chapters_dir = os.path.join(novel_dir, "chapters")
            if not os.path.isdir(chapters_dir):
                print(f"  跳过: {chapters_dir} 不存在")
                continue
            text = process_chapters_dir(chapters_dir, title)
        
        out_name = novel["dir"].split("_", 1)[1] + "_番茄小说版.txt"
        out_path = os.path.join(OUT, out_name)
        
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        
        char_count = len(text)
        chapter_count = sum(1 for line in text.split("\n") if re.match(r'^第\d+章\s', line.strip()))
        
        print(f"  输出: {out_path}")
        print(f"  字数: {char_count}")
        print(f"  章节数: {chapter_count}")
        print()
    
    # Generate combined file
    print("生成合集文件...")
    combined = []
    for novel in NOVELS:
        out_name = novel["dir"].split("_", 1)[1] + "_番茄小说版.txt"
        out_path = os.path.join(OUT, out_name)
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                combined.append(f.read())
            combined.append("\n\n\n")
    
    combined_path = os.path.join(OUT, "重生之动物变身_合集_番茄小说版.txt")
    with open(combined_path, "w", encoding="utf-8") as f:
        f.write("".join(combined))
    
    total_chars = sum(len(c) for c in combined)
    print(f"  合集: {combined_path}")
    print(f"  总字数: {total_chars}")


if __name__ == "__main__":
    main()
