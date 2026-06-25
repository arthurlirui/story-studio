#!/usr/bin/env python3
"""Generate 番茄小说格式 PDF for 《血之契约》"""

import os
import re
from fpdf import FPDF

INPUT_FILE = "/tmp/tomato_full.md"
OUTPUT = "/home/openclaw/.openclaw/workspace/story-studio/output/blood-bond/血之契约_番茄版.pdf"
TEXT_OUTPUT = "/home/openclaw/.openclaw/workspace/story-studio/output/blood-bond/血之契约_番茄版.txt"

FONT_SONG = "/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf"
FONT_KAI = "/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf"


class TomatoPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.add_font('Song', '', FONT_SONG)
        self.add_font('Kai', '', FONT_KAI)
        self.set_auto_page_break(True, 25)
        self.body_indent = 10
        self.dialogue_indent = 18
        self.line_height = 7.5
        self.para_spacing = 1.5

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
        self.cell(0, 10, '—— 番茄小说版 ——', align='C')
        self.ln(15)
        self.set_font('Song', '', 11)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, '十八章 · 尾声', align='C')
        self.ln(8)
        self.cell(0, 8, '文字润色 · 中文标点 · 可直接发表', align='C')
        self.ln(20)
        self.set_font('Kai', '', 12)
        self.cell(0, 10, 'story-studio 作品', align='C')

    def add_chapter_title(self, title):
        self.ln(8)
        self.set_font('Kai', '', 20)
        self.set_text_color(0, 0, 0)
        self.cell(0, 12, title, align='C')
        self.ln(14)

    def write_body(self, text):
        paragraphs = text.split('\n\n')
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Short centered lines (scene breaks)
            if len(para) < 30 and not para.endswith('\u3002'):
                self.set_font('Kai', '', 12)
                self.set_text_color(80, 80, 80)
                self.cell(0, 8, para, align='C')
                self.ln(6)
                continue
            
            # Check if it's dialogue (starts with quote)
            if para.startswith('\u201c'):
                self.set_font('Song', '', 11)
                self.set_text_color(30, 30, 30)
                self.cell(self.dialogue_indent, 0, '')
                self.multi_cell(0, self.line_height, para, align='L')
                self.ln(self.para_spacing)
            else:
                self.set_font('Song', '', 11)
                self.set_text_color(30, 30, 30)
                self.cell(self.body_indent, 0, '')
                self.multi_cell(0, self.line_height, para, align='L')
                self.ln(self.para_spacing)


def main():
    # Also save as plain text for easy copy-paste
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Save plain text version (remove markdown # headers)
    text_content = re.sub(r'^# ', '', content, flags=re.MULTILINE)
    with open(TEXT_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(text_content)
    
    print(f"✅ 纯文本版: {TEXT_OUTPUT}")
    print(f"   大小: {os.path.getsize(TEXT_OUTPUT) / 1024:.1f} KB")
    
    # Generate PDF
    pdf = TomatoPDF()
    pdf.add_title_page()
    
    # Split by chapter markers
    chapter_pattern = re.compile(r'^# (第[^：]+[ ：][^\n]+|尾声[ ：][^\n]+)', re.MULTILINE)
    sections = chapter_pattern.split(content)
    
    current_chapter = None
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        
        if i > 0 and i % 2 == 1:
            current_chapter = section
            pdf.add_page()
            pdf.add_chapter_title(section)
        elif i > 0 and i % 2 == 0:
            pdf.write_body(section)
            print(f"  ✓ {current_chapter}")
    
    pdf.output(OUTPUT)
    print(f"\n✅ PDF: {OUTPUT}")
    print(f"   大小: {os.path.getsize(OUTPUT) / 1024:.1f} KB")
    print(f"   页数: {pdf.page_no()}")


if __name__ == '__main__':
    main()
