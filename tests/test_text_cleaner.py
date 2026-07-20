"""单元测试：agents/text_cleaner.py 的纯函数清洗逻辑。

覆盖：
- clean_chapter_body：各类 markdown 标记的去除（图片、加粗、斜体、引用、
  分隔线、子标题、段落编号、章末标记、空行归一、尾空白）
- strip_existing_title：H1 标题剥离 / 无标题 / ## 开头不当 H1
- 边界：空字符串、只有标题无正文、嵌套标记
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 tests/ 能 import 项目根模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.text_cleaner import clean_chapter_body, strip_existing_title


# ── clean_chapter_body ───────────────────────────────────────


class TestCleanChapterBody:
    def test_empty_string(self):
        assert clean_chapter_body("") == ""

    def test_plain_text_unchanged(self):
        text = "这是一段普通文本。\n\n第二段。"
        assert clean_chapter_body(text) == "这是一段普通文本。\n\n第二段。"

    def test_image_placeholder_removed(self):
        text = "前文\n\n![插图](http://example.com/x.png)\n\n后文"
        out = clean_chapter_body(text)
        assert "![" not in out
        assert "example.com" not in out
        assert "前文" in out and "后文" in out

    def test_bold_keeps_inner_text(self):
        assert clean_chapter_body("**加粗**内容") == "加粗内容"

    def test_italic_keeps_inner_text(self):
        assert clean_chapter_body("*斜体*内容") == "斜体内容"

    def test_bold_and_italic(self):
        assert clean_chapter_body("**粗**与*斜*") == "粗与斜"

    def test_blockquote_prefix_removed(self):
        text = ">引用第一行\n>引用第二行"
        out = clean_chapter_body(text)
        assert ">" not in out
        assert "引用第一行" in out and "引用第二行" in out

    def test_hrule_removed(self):
        text = "上文\n---\n下文"
        out = clean_chapter_body(text)
        assert "---" not in out
        assert "上文" in out and "下文" in out

    def test_hrule_asterisk_removed(self):
        text = "上文\n***\n下文"
        out = clean_chapter_body(text)
        assert "***" not in out

    def test_subheading_prefix_removed_keeps_text(self):
        text = "## 子标题\n正文"
        out = clean_chapter_body(text)
        assert "##" not in out
        assert "子标题" in out
        assert "正文" in out

    def test_paragraph_number_dot_removed(self):
        assert clean_chapter_body("1. 第一段\n2. 第二段") == "第一段\n第二段"

    def test_paragraph_number_chinese_comma_removed(self):
        assert clean_chapter_body("1、第一段\n2、第二段") == "第一段\n第二段"

    def test_paragraph_circled_number_removed(self):
        assert clean_chapter_body("①第一段\n②第二段") == "第一段\n第二段"

    def test_paragraph_paren_number_removed(self):
        # 半角 (1)
        assert clean_chapter_body("(1)第一段\n(2)第二段") == "第一段\n第二段"
        # 全角 （1）
        assert clean_chapter_body("（1）第一段\n（2）第二段") == "第一段\n第二段"

    def test_chapter_end_marker_removed(self):
        text = "正文\n\n*——第十八章完——*\n"
        out = clean_chapter_body(text)
        assert "完——" not in out
        assert "*——" not in out
        assert "正文" in out

    def test_multi_newline_collapsed(self):
        text = "段一\n\n\n\n\n段二"
        assert clean_chapter_body(text) == "段一\n\n段二"

    def test_trailing_whitespace_removed(self):
        text = "行一   \n行二\t\n"
        out = clean_chapter_body(text)
        for line in out.splitlines():
            assert line == line.rstrip()

    def test_nested_markdown(self):
        text = "## 子标题\n\n**粗体**段落\n\n1. 编号\n\n![图](x.png)\n\n---\n\n*——完——*"
        out = clean_chapter_body(text)
        assert "##" not in out
        assert "**" not in out
        assert "![" not in out
        assert "---" not in out
        assert "*——" not in out
        assert "1." not in out
        assert "子标题" in out and "粗体" in out and "编号" in out

    def test_leading_whitespace_in_paragraph_number(self):
        # 行首有空格仍应被识别为段落编号
        assert clean_chapter_body("  1. 第一段") == "第一段"

    def test_bracket_end_marker_removed(self):
        # 全角方括号章末标记 【第一章完】/【完】
        text = "正文内容\n\n【第一章完】\n后续"
        out = clean_chapter_body(text)
        assert "【" not in out, "TXT 仍含 【】 章末标记"
        assert "完】" not in out
        assert "正文内容" in out and "后续" in out

    def test_bracket_end_marker_simple(self):
        # 仅 【完】 也应被去除
        assert "完】" not in clean_chapter_body("正文。\n\n【完】\n")

    def test_self_check_block_removed(self):
        # LLM 自检块：## 章节自检 + task list 行，整块剥离
        text = (
            "正文段落一。\n\n"
            "## 章节自检\n"
            "- [x] 爽点：主角觉醒\n"
            "- [ ] 字数：约5200字\n\n"
            "下一章开始。"
        )
        out = clean_chapter_body(text)
        assert "章节自检" not in out, "TXT 仍含自检块标题"
        assert "爽点" not in out, "TXT 仍含自检块元信息"
        assert "[x]" not in out and "[ ]" not in out
        assert "正文段落一" in out and "下一章开始" in out

    def test_self_check_block_variant_name(self):
        # "## 自检"（不带"章节"）也应被剥离
        text = "正文。\n\n## 自检\n- [x] 检查通过\n\n结尾。"
        out = clean_chapter_body(text)
        assert "自检" not in out
        assert "检查通过" not in out
        assert "正文" in out and "结尾" in out

    def test_task_list_marker_removed(self):
        # 散落的 task list 行（不在自检块内）也应去除
        text = "正文一。\n\n- [x] 某个 checklist 项\n\n正文二。"
        out = clean_chapter_body(text)
        assert "[x]" not in out
        assert "checklist" not in out
        assert "正文一" in out and "正文二" in out

    def test_normal_bullet_list_preserved(self):
        # 普通无序列表（- 项，无 [x]）不应被误删
        text = "正文。\n\n- 普通列表项\n- 另一项\n\n结尾。"
        out = clean_chapter_body(text)
        assert "普通列表项" in out, "普通列表项被误删"
        assert "另一项" in out


# ── strip_existing_title ─────────────────────────────────────


class TestStripExistingTitle:
    def test_empty_string(self):
        assert strip_existing_title("") == ("", "")

    def test_with_h1_title(self):
        text = "# 第 1 章 废柴之名\n\n正文开始。"
        title, body = strip_existing_title(text)
        assert title == "第 1 章 废柴之名"
        assert body == "正文开始。"

    def test_without_title(self):
        text = "正文直接开始。\n\n第二段。"
        title, body = strip_existing_title(text)
        assert title == ""
        assert body == text

    def test_h2_not_treated_as_h1(self):
        # ## 子标题不应被当作 H1 标题剥离
        text = "## 子标题\n正文"
        title, body = strip_existing_title(text)
        assert title == ""
        assert body == text

    def test_only_title_no_body(self):
        text = "# 只有标题"
        title, body = strip_existing_title(text)
        assert title == "只有标题"
        assert body == ""

    def test_title_with_trailing_spaces(self):
        text = "# 标题   \n\n正文"
        title, body = strip_existing_title(text)
        assert title == "标题"
        assert body == "正文"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
