"""outline_format 单测：解析容错 + 渲染往返一致性 + 与下游解析器的兼容性锁定。

渲染格式是前端大纲编辑器与写作流水线之间的契约：
- extract_chapter_outline 必须能切出每一章
- StoryOrchestrator._parse_total_chapters 必须能数出总章数
修改 render_outline 前先确认这些测试仍通过。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from outline_format import (
    ChapterOutline,
    OutlineDoc,
    parse_outline,
    render_outline,
    _cn_to_int,
)

# 仓库内的真实大纲样例
SAMPLE_OUTLINE = Path(__file__).parent.parent / "story" / "outline.md"

# 渲染格式样例（与 _render_chapter 的输出一致）
RENDERED_SAMPLE = """\
# 《玉璧之战》章节大纲

**设计说明：**
节奏螺旋上升。

## 第1章：黑云压城

*   **核心事件**：
    1.  **感官压迫**：东魏大军压境。
    2.  **无声对峙**：高欢审视地图。
*   **出场角色**：韦孝宽、高欢、斛律金
*   **章节悬念/钩子**：高欢下令“三日破城”。
*   **字数预估**：2500字

## 第2章：断水与火海

*   **核心事件**：
    1.  水源切断。
*   **出场角色**：韦孝宽、李元忠
*   **章节悬念/钩子**：秋雨将至。
*   **字数预估**：2800字
"""


# ── 中文数字 ─────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("一", 1), ("十", 10), ("十一", 11), ("二十", 20), ("二十三", 23),
    ("百", 100), ("一百", 100), ("一百零一", 101), ("二百三十", 230),
    ("999", 999), ("12", 12), ("", None), ("abc", None),
])
def test_cn_to_int(raw, expected):
    assert _cn_to_int(raw) == expected


# ── 解析 ─────────────────────────────────────────────────────


def test_parse_empty():
    for empty in ("", "   \n  ", None):
        doc = parse_outline(empty or "")
        assert doc.book_title == ""
        assert doc.preamble == ""
        assert doc.chapters == []


def test_parse_rendered_sample():
    doc = parse_outline(RENDERED_SAMPLE)
    assert doc.book_title == "玉璧之战"
    assert "节奏螺旋上升" in doc.preamble
    assert len(doc.chapters) == 2

    ch1 = doc.chapters[0]
    assert ch1.num == 1
    assert ch1.title == "黑云压城"
    assert len(ch1.events) == 2
    assert ch1.events[0].startswith("**感官压迫**")
    assert ch1.characters == ["韦孝宽", "高欢", "斛律金"]
    assert ch1.hook == "高欢下令“三日破城”。"
    assert ch1.word_estimate == 2500

    assert doc.chapters[1].num == 2
    assert doc.chapters[1].word_estimate == 2800


def test_parse_real_sample_outline():
    """用仓库真实 AI 生成的大纲验证解析。"""
    if not SAMPLE_OUTLINE.exists():
        pytest.skip("story/outline.md 不存在")
    doc = parse_outline(SAMPLE_OUTLINE.read_text(encoding="utf-8"))
    assert len(doc.chapters) >= 7, f"应解析出至少 7 章，实际 {len(doc.chapters)}"
    ch1 = doc.chapters[0]
    assert ch1.num == 1
    assert ch1.title == "黑云压城"
    assert ch1.events, "第一章应有核心事件"
    assert "韦孝宽" in ch1.characters
    assert ch1.word_estimate == 2500


def test_parse_chinese_chapter_numbers():
    md = "## 第一章：开局\n\n*   **字数预估**：2000字\n\n## 第十二章：转折\n"
    doc = parse_outline(md)
    assert [c.num for c in doc.chapters] == [1, 12]


def test_parse_inline_values():
    """字段值与标记同行时也应正确解析。"""
    md = """\
## 第1章：测试

- 核心事件：事件A
- 出场角色：张三、李四
- 悬念/钩子：留个悬念
- 字数预估：3000字
"""
    doc = parse_outline(md)
    ch = doc.chapters[0]
    assert ch.events == ["事件A"]
    assert ch.characters == ["张三", "李四"]
    assert ch.hook == "留个悬念"
    assert ch.word_estimate == 3000


def test_parse_missing_fields_defaults():
    md = "## 第3章：只有标题\n"
    doc = parse_outline(md)
    ch = doc.chapters[0]
    assert ch.num == 3
    assert ch.title == "只有标题"
    assert ch.events == []
    assert ch.characters == []
    assert ch.hook == ""
    assert ch.word_estimate == 2500


def test_parse_no_chapters_all_preamble():
    doc = parse_outline("这是一段普通文本，没有章节结构。\n\n第二段。")
    assert doc.chapters == []
    assert "没有章节结构" in doc.preamble


# ── 渲染 + 往返一致性 ─────────────────────────────────────────


def test_roundtrip_stability():
    """parse(render(doc)) == doc：结构化编辑器保存后语义不变。"""
    doc = parse_outline(RENDERED_SAMPLE)
    assert parse_outline(render_outline(doc)) == doc


def test_roundtrip_real_sample():
    """真实样例：一次规整化后再往返应完全稳定。"""
    if not SAMPLE_OUTLINE.exists():
        pytest.skip("story/outline.md 不存在")
    doc = parse_outline(SAMPLE_OUTLINE.read_text(encoding="utf-8"))
    normalized = parse_outline(render_outline(doc))
    assert parse_outline(render_outline(normalized)) == normalized


def test_render_empty_doc():
    assert render_outline(OutlineDoc()) == ""


def test_render_skips_empty_fields():
    doc = OutlineDoc(chapters=[ChapterOutline(num=1, title="空白章")])
    md = render_outline(doc)
    assert "## 第1章：空白章" in md
    doc2 = parse_outline(md)
    assert doc2.chapters[0].events == []
    assert doc2.chapters[0].characters == []
    assert doc2.chapters[0].word_estimate == 2500


# ── 与下游解析器的兼容性锁定 ─────────────────────────────────


def test_rendered_compatible_with_extract_chapter_outline():
    """渲染产物必须能被 agents.utils.extract_chapter_outline 切片。"""
    from agents.utils import extract_chapter_outline

    doc = parse_outline(RENDERED_SAMPLE)
    md = render_outline(doc)
    for ch in doc.chapters:
        slice_ = extract_chapter_outline(md, ch.num)
        assert ch.title in slice_, f"第{ch.num}章切片应含标题"
        assert "字数预估" in slice_


def test_rendered_compatible_with_total_chapters_parser():
    """渲染产物必须能被 _parse_total_chapters 数出总章数。"""
    orchestrator = pytest.importorskip("orchestrator")
    doc = parse_outline(RENDERED_SAMPLE)
    md = render_outline(doc) + "\n## 第3章：尾声\n"
    assert orchestrator.StoryOrchestrator._parse_total_chapters(md) == 3
