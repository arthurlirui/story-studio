#!/usr/bin/env python3
"""Generate PDF for 《血之契约》 with proper dialogue alignment and Chinese typography."""

import os
import re
from pathlib import Path
from fpdf import FPDF

CHAPTER_DIR = str(Path(__file__).resolve().parent / "knowledge" / "story" / "chapters")
OUTPUT = str(Path(__file__).resolve().parent / "output" / "blood-bond" / "血之契约.pdf")

FONT_SONG = "/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf"
FONT_KAI = "/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf"

CHAPTERS = [
    "chapter_001.md", "chapter_002.md", "chapter_003.md", "chapter_004.md",
    "chapter_005.md", "chapter_006.md", "chapter_007.md", "chapter_008.md",
    "chapter_009.md", "chapter_010.md", "chapter_011.md", "chapter_012.md",
    "chapter_013.md", "chapter_014.md", "chapter_015.md", "chapter_016.md",
    "chapter_017.md", "chapter_018.md", "chapter_epilogue.md",
]

CHAPTER_TITLES = {
    "chapter_001.md": "第一章  暗夜中的猎物",
    "chapter_002.md": "第二章  铁笼与玫瑰",
    "chapter_003.md": "第三章  蜘蛛的第一根丝",
    "chapter_004.md": "第四章  血色月光",
    "chapter_005.md": "第五章  血契",
    "chapter_006.md": "第六章  选择留下",
    "chapter_007.md": "第七章  狼嚎之夜",
    "chapter_008.md": "第八章  月光下的陌生人",
    "chapter_009.md": "第九章  两个世界之间",
    "chapter_010.md": "第十章  三角测量",
    "chapter_011.md": "第十一章  裂痕",
    "chapter_012.md": "第十二章  命运伴侣的赌注",
    "chapter_013.md": "第十三章  血与火",
    "chapter_014.md": "第十四章  面具之下",
    "chapter_015.md": "第十五章  拒绝",
    "chapter_016.md": "第十六章  家族审判",
    "chapter_017.md": "第十七章  废墟",
    "chapter_018.md": "第十八章  血之盛宴",
    "chapter_epilogue.md": "尾声  月光下的倒影",
}

VOLUMES = {
    "chapter_001.md": "第一幕  囚笼与蜜糖",
    "chapter_007.md": "第二幕  救赎与背叛",
    "chapter_013.md": "第三幕  血之盛宴",
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
    # Remove editor notes
    text = re.sub(r'---+\s*\n?\*\*\[编辑批注\]\*\*.*', '', text, flags=re.DOTALL)
    text = re.sub(r'\*\*\[连续性检查\]\*\*.*', '', text, flags=re.DOTALL)
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
            self.cell(0, 8, '血之契约', align='C')
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
        self.cell(0, 10, '—— 一部暗黑哥特式浪漫小说 ——', align='C')
        self.ln(20)
        self.set_font('Kai', '', 12)
        self.cell(0, 10, 'story-studio 作品', align='C')
        self.ln(20)
        self.set_font('Song', '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, '三幕 · 十八章 · 尾声', align='C')
        self.ln(8)
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

    for ch_file in CHAPTERS:
        ch_path = os.path.join(CHAPTER_DIR, ch_file)
        if not os.path.exists(ch_path):
            print(f"SKIP: {ch_file} not found")
            continue

        if ch_file in VOLUMES:
            pdf.add_volume_title(VOLUMES[ch_file])

        ch_title = CHAPTER_TITLES.get(ch_file, ch_file.replace('.md', '').replace('_', ' '))
        pdf.add_page()
        pdf.add_chapter_title(ch_title)

        with open(ch_path, 'r', encoding='utf-8') as f:
            raw = f.read()

        text = strip_markdown(raw)
        pdf.add_body_text(text)
        print(f"  ✓ {ch_title}")

    pdf.output(OUTPUT)
    file_size = os.path.getsize(OUTPUT)
    print(f"\n✅ PDF generated: {OUTPUT}")
    print(f"   Size: {file_size / 1024:.1f} KB")
    print(f"   Pages: {pdf.page_no()}")


if __name__ == '__main__':
    main()
