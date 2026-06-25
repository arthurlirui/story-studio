#!/usr/bin/env python3
"""
全面修复《血之契约》润色版文本格式，适配番茄小说发表格式。

修复项：
1. 英文引号 " → 中文引号 ""（成对转换）
2. 去除所有 markdown 标记（*斜体*、**粗体**）
3. 章节标题统一格式
4. 规范化空行（段落间最多1个空行）
5. 去除章节末尾的 *——XX章完——*
6. 去除多余的水平线 ---
"""

import re
import os

CHAPTERS_DIR = "/home/openclaw/.openclaw/workspace/story-studio/output/blood-bond"
OUTPUT_DIR = "/home/openclaw/.openclaw/workspace/story-studio/output/blood-bond/tomato"

os.makedirs(OUTPUT_DIR, exist_ok=True)

CHAPTER_FILES = [
    "第一章_暗夜坠入_润色.md",
    "第二章_猎物与猎人_润色.md",
    "第三章_蜘蛛的第一根丝_润色.md",
    "第四章_血色月光_润色.md",
    "第五章_血契_润色.md",
    "第六章_选择留下_润色.md",
    "第七章_狼嚎之夜_润色.md",
    "第八章_月光下的陌生人_润色.md",
    "第九章_两个世界之间_润色.md",
    "第十章_三角测量_润色.md",
    "第十一章_裂痕_润色.md",
    "第十二章_命运伴侣的赌注_润色.md",
    "第十三章_血与火_润色.md",
    "第十四章_面具之下_润色.md",
    "第十五章_拒绝_润色.md",
    "第十六章_家族审判_润色.md",
    "第十七章_废墟_润色.md",
    "第十八章_血之盛宴_润色.md",
    "尾声_月光下的倒影_润色.md",
]

CHAPTER_TITLES = {
    "第一章：暗夜坠入": "第一章 暗夜坠入",
    "第二章：猎物与猎人": "第二章 猎物与猎人",
    "第三章：蜘蛛的第一根丝": "第三章 蜘蛛的第一根丝",
    "第四章：血色月光": "第四章 血色月光",
    "第五章：血契": "第五章 血契",
    "第六章：选择留下": "第六章 选择留下",
    "第七章：狼嚎之夜（润色版）": "第七章 狼嚎之夜",
    "第八章：月光下的陌生人（润色版）": "第八章 月光下的陌生人",
    "第九章：两个世界之间（润色版）": "第九章 两个世界之间",
    "第十章：三角测量（润色版）": "第十章 三角测量",
    "第十一章：裂痕（润色版）": "第十一章 裂痕",
    "第十二章：命运伴侣的赌注（润色版）": "第十二章 命运伴侣的赌注",
    "第十三章：血与火（润色版）": "第十三章 血与火",
    "第十四章：面具之下（润色版）": "第十四章 面具之下",
    "第十五章：拒绝（润色版）": "第十五章 拒绝",
    "第十六章：家族审判（润色版）": "第十六章 家族审判",
    "第十七章：废墟（润色版）": "第十七章 废墟",
    "第十八章：血之盛宴（润色版）": "第十八章 血之盛宴",
    "尾声：月光下的倒影（润色版）": "尾声 月光下的倒影",
}


def fix_english_quotes(text):
    """
    Convert English double quotes to Chinese double quotes.
    Handles nested quotes and paired quotes properly.
    """
    result = []
    quote_stack = []  # Track quote types: 'left' for ", 'right' for "
    
    i = 0
    while i < len(text):
        ch = text[i]
        
        if ch == '"':
            # Check if this is a left or right quote based on context
            if not quote_stack:
                # Opening quote
                result.append('\u201c')  # "
                quote_stack.append('open')
            else:
                # Closing quote
                result.append('\u201d')  # "
                quote_stack.pop()
        else:
            result.append(ch)
        i += 1
    
    return ''.join(result)


def remove_markdown(text):
    """Remove markdown formatting markers."""
    # Remove **bold** markers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove *italic* markers (but not inside Chinese text where * might be decorative)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    return text


def clean_chapter_title(text):
    """Clean and standardize chapter titles."""
    text = text.strip()
    # Remove markdown heading markers
    text = re.sub(r'^#+\s*', '', text)
    # Standardize title
    if text in CHAPTER_TITLES:
        return CHAPTER_TITLES[text]
    # Fallback: remove (润色版) suffix
    text = re.sub(r'（润色版）', '', text)
    # Change ：to space
    text = re.sub(r'：', ' ', text)
    return text.strip()


def normalize_blank_lines(text):
    """Normalize blank lines: max 1 blank line between paragraphs."""
    # Replace 3+ consecutive newlines with 2 newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def remove_horizontal_rules(text):
    """Remove horizontal rule markers (---, ***, etc.)."""
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    return text


def remove_chapter_end_markers(text):
    """Remove *——XX章完——* markers."""
    text = re.sub(r'\*——[^——]+完——\*', '', text)
    return text


def process_file(filename):
    input_path = os.path.join(CHAPTERS_DIR, filename)
    output_filename = filename.replace('_润色.md', '_番茄版.md')
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Step 1: Remove chapter end markers first
    content = remove_chapter_end_markers(content)
    
    # Step 2: Remove horizontal rules
    content = remove_horizontal_rules(content)
    
    # Step 3: Extract and clean chapter title
    lines = content.split('\n')
    title_line = lines[0] if lines else ''
    clean_title = clean_chapter_title(title_line)
    
    # Step 4: Remove the original title line and any leading blank lines
    content = '\n'.join(lines[1:]).strip()
    
    # Step 5: Remove markdown formatting
    content = remove_markdown(content)
    
    # Step 6: Convert English quotes to Chinese quotes
    content = fix_english_quotes(content)
    
    # Step 7: Normalize blank lines
    content = normalize_blank_lines(content)
    
    # Step 8: Remove leading/trailing whitespace from each line
    lines = content.split('\n')
    lines = [line.strip() for line in lines]
    content = '\n'.join(lines)
    
    # Step 9: Normalize blank lines again after stripping
    content = normalize_blank_lines(content)
    
    # Step 10: Remove trailing whitespace
    content = content.strip()
    
    # Rebuild: clean title + content
    final_content = f"# {clean_title}\n\n{content}"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    
    # Count issues fixed
    original_quotes = content.count('\u201c') + content.count('\u201d')
    
    return output_path, original_quotes


def main():
    total_quotes = 0
    for filename in CHAPTER_FILES:
        output_path, quotes = process_file(filename)
        total_quotes += quotes
        print(f"  ✓ {filename} → {os.path.basename(output_path)} ({quotes} 对中文引号)")
    
    print(f"\n✅ 全部 {len(CHAPTER_FILES)} 个文件处理完成")
    print(f"   共转换 {total_quotes} 对中文引号")
    print(f"   输出目录: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
