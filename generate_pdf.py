#!/usr/bin/env python3
"""Generate PDF for 《刘寄奴传》 with proper dialogue alignment and Chinese typography."""

import os
import re
from pathlib import Path
from fpdf import FPDF

CHAPTER_DIR = str(Path(__file__).resolve().parent / "刘裕传")
OUTPUT = str(Path(__file__).resolve().parent / "刘裕传" / "刘寄奴传.pdf")

FONT_SONG = "/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf"
FONT_KAI = "/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf"

CHAPTERS = [
    "第01章_寒门遗孤.md", "第02章_江畔草履.md", "第03章_北府从戎.md",
    "第04章_三吴烽火.md", "第05章_潜龙勿用.md", "第06章_覆舟之战.md",
    "第07章_土断风云.md", "第08章_铁骑灭燕.md", "第09章_千里回师.md",
    "第10章_手足相残.md", "第11章_却月奇阵.md", "第12章_长安遗恨.md",
    "第13章_受禅开国.md", "第14章_血染乌衣.md", "第15章_魂归京口.md",
    "尾声_草鞋犹在.md",
]

VOLUMES = {
    "第01章": "卷一  京口少年",
    "第04章": "卷二  乱世锋镝",
    "第07章": "卷三  权倾江左",
    "第11章": "卷四  气吞万里",
    "第13章": "卷五  孤家寡人",
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
    # Line starts with Chinese quote
    if stripped.startswith('\u201c') or stripped.startswith('\u300c'):
        return True
    # Line contains substantial quoted dialogue
    quote_count = stripped.count('\u201c') + stripped.count('\u201d')
    if quote_count >= 2 and len(stripped) > 10:
        return True
    return False

def is_narrative_with_dialogue(line):
    """Line has both narrative and dialogue mixed."""
    stripped = line.strip()
    if not stripped:
        return False
    # Contains quotes but doesn't start with one
    has_quote = '\u201c' in stripped or '\u300c' in stripped
    starts_with_quote = stripped.startswith('\u201c') or stripped.startswith('\u300c')
    return has_quote and not starts_with_quote

def split_dialogue_paragraph(para):
    """Split a paragraph into narrative and dialogue segments for better alignment."""
    # Pattern: narrative text "dialogue" more narrative
    parts = re.split(r'(\u201c[^\u201d]*\u201d)', para)
    return [p for p in parts if p.strip()]

class LiuYuPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.add_font('Song', '', FONT_SONG)
        self.add_font('Kai', '', FONT_KAI)
        self.set_auto_page_break(True, 25)
        self.body_indent = 22  # 2-char indent for body text
        self.dialogue_indent = 33  # 3-char indent for pure dialogue
        self.line_height = 7.5
        self.para_spacing = 2

    def header(self):
        if self.page_no() > 1:
            self.set_font('Kai', '', 9)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, '刘寄奴传', align='C')
            self.ln(12)

    def footer(self):
        self.set_y(-20)
        self.set_font('Song', '', 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, str(self.page_no()), align='C')

    def add_title_page(self):
        self.add_page()
        self.ln(60)
        self.set_font('Kai', '', 48)
        self.set_text_color(0, 0, 0)
        self.cell(0, 20, '刘 寄 奴 传', align='C')
        self.ln(30)
        self.set_font('Song', '', 14)
        self.set_text_color(80, 80, 80)
        self.cell(0, 10, '\u2014\u2014 \u4e00\u90e8\u5173\u4e8e\u201c\u51e0\u4e4e\u6210\u529f\u201d\u7684\u60b2\u5267 \u2014\u2014', align='C')
        self.ln(20)
        self.set_font('Kai', '', 12)
        self.cell(0, 10, 'story-studio \u4f5c\u54c1', align='C')
        self.ln(10)
        self.cell(0, 10, '\u5c71\u5188\u5e84\u516b\u5f0f\u7b14\u6cd5 \u00b7 \u4e2d\u7bc7\u5386\u53f2\u5c0f\u8bf4', align='C')
        self.ln(40)
        self.set_font('Song', '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, '\u4e94\u5377 \u00b7 \u5341\u4e94\u7ae0 \u00b7 \u5c3e\u58f0', align='C')
        self.ln(8)
        self.cell(0, 8, '\u4ece\u4eac\u53e3\u5356\u8349\u978b\u7684\u5c11\u5e74\u5230\u5357\u671d\u7b2c\u4e00\u5e1d', align='C')
        self.ln(8)
        self.cell(0, 8, '\u4ece\u6c14\u541e\u4e07\u91cc\u5230\u529f\u4e8f\u4e00\u7bc1', align='C')

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
        """Write a pure dialogue paragraph with proper indentation."""
        self.set_font('Song', '', 11)
        self.set_text_color(30, 30, 30)
        self.cell(self.dialogue_indent, 0, '')
        self.multi_cell(0, self.line_height, para, align='L')
        self.ln(self.para_spacing)

    def write_narrative_para(self, para):
        """Write a narrative paragraph with standard indent."""
        self.set_font('Song', '', 11)
        self.set_text_color(30, 30, 30)
        self.cell(self.body_indent, 0, '')
        self.multi_cell(0, self.line_height, para, align='L')
        self.ln(self.para_spacing)

    def write_mixed_para(self, para):
        """Write a paragraph that mixes narrative and dialogue.
        Split at quote boundaries for better alignment."""
        self.set_font('Song', '', 11)
        self.set_text_color(30, 30, 30)

        # Split into segments: narrative and quoted dialogue
        segments = re.split(r'(\u201c[^\u201d]*\u201d)', para)
        segments = [s for s in segments if s]

        first_segment = True
        current_line = ""

        for seg in segments:
            is_quote = seg.startswith('\u201c') and seg.endswith('\u201d')

            if first_segment and not is_quote:
                # Leading narrative - standard indent
                combined = seg
                # Check if next segment is a quote
                idx = segments.index(seg)
                if idx + 1 < len(segments) and segments[idx+1].startswith('\u201c'):
                    combined = seg + segments[idx+1]
                    segments[idx+1] = ""  # mark as consumed

                self.cell(self.body_indent, 0, '')
                self.multi_cell(0, self.line_height, combined, align='L')
                first_segment = False
            elif is_quote:
                # Dialogue segment - use dialogue indent
                self.cell(self.dialogue_indent, 0, '')
                self.multi_cell(0, self.line_height, seg, align='L')
            elif seg.strip():
                # Trailing narrative after quote
                self.cell(self.body_indent, 0, '')
                self.multi_cell(0, self.line_height, seg, align='L')

        self.ln(self.para_spacing)

    def add_body_text(self, text):
        """Add body text with dialogue-aware formatting."""
        paragraphs = text.split('\n\n')
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Section divider
            if para.startswith('---') or para.startswith('***'):
                self.ln(4)
                self.set_draw_color(180, 180, 180)
                x = self.get_x() + 60
                self.line(x, self.get_y(), x + 90, self.get_y())
                self.ln(6)
                continue

            # Sub-heading (short line, no period at end)
            if len(para) < 60 and not para.endswith('\u3002') and not para.endswith('\uff0c'):
                self.set_font('Kai', '', 13)
                self.set_text_color(60, 60, 60)
                self.multi_cell(0, 8, para, align='L')
                self.ln(2)
                continue

            # Check dialogue type
            if is_dialogue_line(para):
                self.write_dialogue_para(para)
            elif is_narrative_with_dialogue(para):
                self.write_mixed_para(para)
            else:
                self.write_narrative_para(para)

def main():
    pdf = LiuYuPDF()
    pdf.add_title_page()

    for ch_file in CHAPTERS:
        ch_path = os.path.join(CHAPTER_DIR, ch_file)
        if not os.path.exists(ch_path):
            print(f"SKIP: {ch_file} not found")
            continue

        ch_num = ch_file[:4] if ch_file.startswith('\u7b2c') else '\u5c3e\u58f0'

        if ch_num in VOLUMES:
            pdf.add_volume_title(VOLUMES[ch_num])

        with open(ch_path, 'r', encoding='utf-8') as f:
            raw = f.read()

        title_match = re.match(r'(\u7b2c\d+\u7ae0_|\u5c3e\u58f0_)(.+)\.md', ch_file)
        if title_match:
            if ch_num == '\u5c3e\u58f0':
                ch_title = f"\u5c3e\u58f0\u3000{title_match.group(2)}"
            else:
                ch_title = f"{title_match.group(1).replace('_', ' ')}{title_match.group(2)}"
        else:
            ch_title = ch_file.replace('.md', '')
        ch_title = ch_title.replace('_', '\u3000')

        pdf.add_page()
        pdf.add_chapter_title(ch_title)

        text = strip_markdown(raw)
        pdf.add_body_text(text)
        print(f"  \u2713 {ch_title}")

    pdf.output(OUTPUT)
    file_size = os.path.getsize(OUTPUT)
    print(f"\n\u2705 PDF generated: {OUTPUT}")
    print(f"   Size: {file_size / 1024 / 1024:.1f} MB")
    print(f"   Pages: {pdf.page_no()}")

if __name__ == '__main__':
    main()
