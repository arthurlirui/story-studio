#!/usr/bin/env python3
"""Generate PDF for 《血之契约》润色版 with proper dialogue alignment and Chinese typography."""

import os
import re
from pathlib import Path
from fpdf import FPDF

INPUT_FILE = "/tmp/complete_polished.md"
OUTPUT = "/home/openclaw/.openclaw/workspace/story-studio/output/blood-bond/血之契约_润色版.pdf"

FONT_SONG = "/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf"
FONT_KAI = "/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf"

CHAPTER_TITLES = {
    "第一章：暗夜坠入": "第一章  暗夜坠入",
    "第二章：猎物与猎人": "第二章  猎物与猎人",
    "第三章：蜘蛛的第一根丝": "第三章  蜘蛛的第一根丝",
    "第四章：血色月光": "第四章  血色月光",
    "第五章：血契": "第五章  血契",
    "第六章：选择留下": "第六章  选择留下",
    "第七章：狼嚎之夜（润色版）": "第七章  狼嚎之夜",
    "第八章：月光下的陌生人（润色版）": "第八章  月光下的陌生人",
    "第九章：两个世界之间（润色版）": "第九章  两个世界之间",
    "第十章：三角测量（润色版）": "第十章  三角测量",
    "第十一章：裂痕（润色版）": "第十一章  裂痕",
    "第十二章：命运伴侣的赌注（润色版）": "第十二章  命运伴侣的赌注",
    "第十三章：血与火（润色版）": "第十三章  血与火",
    "第十四章：面具之下（润色版）": "第十四章  面具之下",
    "第十五章：拒绝（润色版）": "第十五章  拒绝",
    "第十六章：家族审判（润色版）": "第十六章  家族审判",
    "第十七章：废墟（润色版）": "第十七章  废墟",
    "第十八章：血之盛宴（润色版）": "第十八章  血之盛宴",
    "尾声：月光下的倒影（润色版）": "尾声  月光下的倒影",
}

VOLUMES = {
    "第七章：狼嚎之夜（润色版）": "第二幕  救赎与背叛",
    "第十三章：血与火（润色版）": "第三幕  血之盛宴",
}


def strip_markdown(text):
    """Remove markdown formatting, keep structure."""
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def is_dialogue_line(line):
    """Check if a line is primarily dialogue (quoted speech)."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith('\u201c') or stripped.startswith('\u300c'):
        return True
    quote_count = stripped.count('\u201c') + stripped.count('\u201d')
    if quote_count >= 2 and len(stripped) > 10:
        return True
    return False


def is_narrative_with_dialogue(line):
    """Line has both narrative and dialogue mixed."""
    stripped = line.strip()
    if not stripped:
        return False
    has_quote = '\u201c' in stripped or '\u300c' in stripped
    starts_with_quote = stripped.startswith('\u201c') or stripped.startswith('\u300c')
    return has_quote and not starts_with_quote


class BloodBondPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.add_font('Song', '', FONT_SONG)
        self.add_font('Kai', '', FONT_KAI)
        self.set_auto_page_break(True, 25)
        self.body_indent = 22
        self.dialogue_indent = 33
        self.line_height = 7.5
        self.para_spacing = 2

    def header(self):
        if self.page_no() > 1:
            self.set_font('Kai', '', 9)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, '血之契约（润色版）', align='C')
            self.ln(12)

    def footer(self):
        self.set_y(-20)
        self.set_font('Song', '', 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, str(self.page_no()), align='C')

    def add_title_page(self):
        self.add_page()
        self.ln(50)
        self.set_font('Kai', '', 48)
        self.set_text_color(0, 0, 0)
        self.cell(0, 20, '血  之  契  约', align='C')
        self.ln(25)
        self.set_font('Song', '', 14)
        self.set_text_color(80, 80, 80)
        self.cell(0, 10, '—— 润色版 ——', align='C')
        self.ln(15)
        self.set_font('Song', '', 11)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, '十八章 · 尾声', align='C')
        self.ln(8)
        self.cell(0, 8, '文字艳丽化 · 人设深化 · 情感操控强化', align='C')
        self.ln(20)
        self.set_font('Kai', '', 12)
        self.cell(0, 10, 'story-studio 作品', align='C')
        self.ln(20)
        self.set_font('Song', '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, '从猎物到猎人，从操控到被囚', align='C')
        self.ln(8)
        self.cell(0, 8, '谁是真正的囚徒？', align='C')

    def add_volume_title(self, title):
        self.add_page()
        self.ln(80)
        self.set_font('Kai', '', 36)
        self.set_text_color(0, 0, 0)
        self.cell(0, 15, title, align='C')
        self.ln(20)
        self.set_draw_color(150, 150, 150)
        x = self.get_x() + 40
        self.line(x, self.get_y(), x + 130, self.get_y())

    def add_chapter_title(self, title):
        self.ln(10)
        self.set_font('Kai', '', 22)
        self.set_text_color(0, 0, 0)
        self.cell(0, 12, title, align='C')
        self.ln(16)

    def write_dialogue_para(self, para):
        self.set_font('Song', '', 11)
        self.set_text_color(30, 30, 30)
        self.cell(self.dialogue_indent, 0, '')
        self.multi_cell(0, self.line_height, para, align='L')
        self.ln(self.para_spacing)

    def write_narrative_para(self, para):
        self.set_font('Song', '', 11)
        self.set_text_color(30, 30, 30)
        self.cell(self.body_indent, 0, '')
        self.multi_cell(0, self.line_height, para, align='L')
        self.ln(self.para_spacing)

    def write_mixed_para(self, para):
        self.set_font('Song', '', 11)
        self.set_text_color(30, 30, 30)
        segments = re.split(r'(\u201c[^\u201d]*\u201d)', para)
        segments = [s for s in segments if s]
        first_segment = True
        for seg in segments:
            is_quote = seg.startswith('\u201c') and seg.endswith('\u201d')
            if first_segment and not is_quote:
                combined = seg
                idx = segments.index(seg)
                if idx + 1 < len(segments) and segments[idx+1].startswith('\u201c'):
                    combined = seg + segments[idx+1]
                    segments[idx+1] = ""
                self.cell(self.body_indent, 0, '')
                self.multi_cell(0, self.line_height, combined, align='L')
                first_segment = False
            elif is_quote:
                self.cell(self.dialogue_indent, 0, '')
                self.multi_cell(0, self.line_height, seg, align='L')
            elif seg.strip():
                self.cell(self.body_indent, 0, '')
                self.multi_cell(0, self.line_height, seg, align='L')
        self.ln(self.para_spacing)

    def add_body_text(self, text):
        paragraphs = text.split('\n\n')
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if para.startswith('---') or para.startswith('***'):
                self.ln(4)
                self.set_draw_color(180, 180, 180)
                x = self.get_x() + 60
                self.line(x, self.get_y(), x + 90, self.get_y())
                self.ln(6)
                continue
            if len(para) < 60 and not para.endswith('\u3002') and not para.endswith('\uff0c') and not para.endswith('"') and not para.endswith('\u201d'):
                self.set_font('Kai', '', 13)
                self.set_text_color(60, 60, 60)
                self.multi_cell(0, 8, para, align='L')
                self.ln(2)
                continue
            if is_dialogue_line(para):
                self.write_dialogue_para(para)
            elif is_narrative_with_dialogue(para):
                self.write_mixed_para(para)
            else:
                self.write_narrative_para(para)


def main():
    pdf = BloodBondPDF()
    pdf.add_title_page()

    # Read the complete file
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by chapter markers
    chapter_pattern = re.compile(r'^# (第[^：]+：[^\n]+|尾声：[^\n]+)', re.MULTILINE)
    sections = chapter_pattern.split(content)
    # sections[0] is the title/header, then alternating [title, body, title, body, ...]

    current_chapter_title = None
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # Check if this is a chapter title
        if i > 0 and i % 2 == 1:
            # This is a chapter title
            current_chapter_title = section
            # Check for volume
            if section in VOLUMES:
                pdf.add_volume_title(VOLUMES[section])
            # Clean title for display
            display_title = CHAPTER_TITLES.get(section, section)
            pdf.add_page()
            pdf.add_chapter_title(display_title)
        elif i > 0 and i % 2 == 0:
            # This is chapter body
            text = strip_markdown(section)
            pdf.add_body_text(text)
            print(f"  ✓ {current_chapter_title}")

    pdf.output(OUTPUT)
    file_size = os.path.getsize(OUTPUT)
    print(f"\n✅ PDF generated: {OUTPUT}")
    print(f"   Size: {file_size / 1024:.1f} KB")
    print(f"   Pages: {pdf.page_no()}")


if __name__ == '__main__':
    main()
