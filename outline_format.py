"""大纲结构化解析/渲染 - 前端大纲编辑器的格式契约层。

大纲本体是 Markdown（knowledge/story/outline.md），每章约定五要素：
章节标题 / 核心事件 / 出场角色 / 章节悬念钩子 / 字数预估。
另有可选的「时代」字段（时代/时间点/年代），供热词研究员按章节时间点检索网络热词。

本模块提供 parse_outline / render_outline 双向转换：
- parse 容错：字段缺失给默认值；不含章节头的文本整体视为 preamble
- render 严格：输出可被 orchestrator._parse_total_chapters /
  agents.utils.extract_chapter_outline 等现有正则正确解析的格式

契约由 tests/test_outline_format.py 的往返一致性测试锁定，
修改渲染格式前必须确认下游解析器仍兼容。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 默认字数预估（与 prompts 中的常见约定一致）
DEFAULT_WORD_ESTIMATE = 2500

# 中文数字 -> int（1-999；逻辑移植自 orchestrator._cn_to_int，本模块保持轻依赖）
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(s: str) -> int | None:
    """中文数字转 int（1-999），纯阿拉伯数字直接返回。无法解析返回 None。"""
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "百" in s:
        bai_idx = s.find("百")
        head = s[:bai_idx]
        hundreds = _CN_DIGITS[head] if head else 1
        tail = s[bai_idx + 1:]
        if not tail:
            return hundreds * 100
        if tail.startswith("零"):
            tail = tail[1:]
            if len(tail) != 1 or tail not in _CN_DIGITS:
                return None
            return hundreds * 100 + _CN_DIGITS[tail]
        tail_val = _cn_to_int(tail)
        if tail_val is None or tail_val >= 100:
            return None
        return hundreds * 100 + tail_val
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    if len(s) == 2 and s[0] == "十":
        return 10 + _CN_DIGITS.get(s[1], 0)
    if len(s) == 2 and s[1] == "十":
        return _CN_DIGITS.get(s[0], 0) * 10
    if len(s) == 3 and s[1] == "十":
        return _CN_DIGITS.get(s[0], 0) * 10 + _CN_DIGITS.get(s[2], 0)
    return None


# 章节头：## 第N章：标题 / ## 第N章 标题 / ## N. 标题 / ## Chapter N（支持中文数字）
_CHAPTER_HEAD_RE = re.compile(
    r"^(?P<hashes>#{1,6})\s+"
    r"(?:"
    r"第\s*(?P<cn>[一二三四五六七八九十百零\d]+)\s*章\s*[:：\s]*\s*(?P<title_cn>.*)"
    r"|(?P<arabic>\d+)\s*[\.\、]\s*(?P<title_ar>.*)"
    r"|Chapter\s*(?P<en>\d+)\b\s*[:：\s]*(?P<title_en>.*)"
    r")\s*$",
    re.MULTILINE,
)

# 章内字段标记：**核心事件**：…（加粗/列表前缀/冒号均可省，行内可带值）
# era 字段为可选，支持 时代/时间点/年代 三种标签写法
_FIELD_RE = re.compile(
    r"^(?:[*+\-]\s*)?\**\s*"
    r"(?P<label>核心事件|出场角色|(?:章节)?悬念(?:\s*[/／]\s*钩子)?|钩子|字数预估|时代|时间点|年代)"
    r"\s*\**\s*[:：]?\s*(?P<inline>.*)$"
)

# 事件条目的列表前缀（* / - / 1. / 1、等）
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[*+\-]\s*)?(?:\d+\s*[\.、\)]\s*)?")

# 出场角色分隔符
_CHAR_SPLIT_RE = re.compile(r"[、，,;；]")

# H1 书名行：# 《书名》xxx
_BOOK_TITLE_RE = re.compile(r"^#\s+《(?P<title>[^》]+)》.*$", re.MULTILINE)


@dataclass
class ChapterOutline:
    """单章大纲的要素。era 为可选的时间点/时代标注，供热词注入按章节时代查表。"""
    num: int = 0
    title: str = ""
    events: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    hook: str = ""
    word_estimate: int = DEFAULT_WORD_ESTIMATE
    era: str = ""


@dataclass
class OutlineDoc:
    """整份大纲：书名 + 设计说明（preamble）+ 章节列表。"""
    book_title: str = ""
    preamble: str = ""
    chapters: list[ChapterOutline] = field(default_factory=list)


def parse_outline(md: str) -> OutlineDoc:
    """把大纲 Markdown 解析为 OutlineDoc。

    容错策略：无章节头时 chapters 为空、全文进 preamble；
    章内字段缺失用默认值填充，保证前端编辑器始终可渲染。
    """
    doc = OutlineDoc()
    if not md or not md.strip():
        return doc

    heads = list(_CHAPTER_HEAD_RE.finditer(md))
    if not heads:
        doc.preamble = _strip_book_title_heading(md).strip()
        doc.book_title = _find_book_title(md)
        return doc

    doc.book_title = _find_book_title(md)
    preamble_raw = md[: heads[0].start()]
    doc.preamble = _strip_book_title_heading(preamble_raw).strip()

    for i, head in enumerate(heads):
        body_end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        doc.chapters.append(_parse_chapter_block(head, md[head.end():body_end]))
    return doc


def render_outline(doc: OutlineDoc) -> str:
    """把 OutlineDoc 渲染回大纲 Markdown。

    渲染格式必须保持与下游解析器兼容（tests/test_outline_format.py 锁定）：
    章节头用 `## 第N章：标题`（阿拉伯数字），字段用加粗标签。
    """
    parts: list[str] = []
    if doc.book_title:
        parts.append(f"# 《{doc.book_title}》章节大纲")
    if doc.preamble:
        parts.append(doc.preamble)
    for ch in doc.chapters:
        parts.append(_render_chapter(ch))
    return "\n\n".join(parts) + ("\n" if parts else "")


# ── 内部实现 ─────────────────────────────────────────────────


def _find_book_title(md: str) -> str:
    """提取书名：优先 orchestrator 约定的「推荐主标题/书名候选」区块，回退 H1 书名行。"""
    m = re.search(r"推荐主标题[\s\S]{0,80}?《([^》]+)》", md)
    if m:
        return m.group(1).strip()
    m = re.search(r"书名候选[\s\S]{0,200}?《([^》]+)》", md)
    if m:
        return m.group(1).strip()
    m = _BOOK_TITLE_RE.search(md)
    if m:
        return m.group("title").strip()
    return ""


def _strip_book_title_heading(text: str) -> str:
    """从 preamble 中去掉 H1 书名行（该书名已单独存入 book_title）。"""
    return _BOOK_TITLE_RE.sub("", text, count=1)


def _parse_chapter_block(head: re.Match, body: str) -> ChapterOutline:
    num_raw = head.group("cn") or head.group("arabic") or head.group("en")
    num = _cn_to_int(num_raw) if num_raw else None
    title = (head.group("title_cn") or head.group("title_ar")
             or head.group("title_en") or "").strip()

    # 按字段标记切块（body 为去掉章节头行后的正文）
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        fm = _FIELD_RE.match(stripped)
        if fm:
            label = fm.group("label")
            # 「章节悬念/钩子」与「钩子」归一化为 hook；时代/时间点/年代 → era
            if "钩子" in label or "悬念" in label:
                current = "hook"
            elif label == "核心事件":
                current = "events"
            elif label == "出场角色":
                current = "characters"
            elif label == "字数预估":
                current = "word_estimate"
            else:  # 时代 / 时间点 / 年代
                current = "era"
            bucket = fields.setdefault(current, [])
            inline = fm.group("inline").strip()
            if inline:
                bucket.append(inline)
            continue
        if current:
            fields[current].append(stripped)

    events = [_LIST_PREFIX_RE.sub("", e).strip() for e in fields.get("events", [])]
    events = [e for e in events if e]

    char_text = "".join(fields.get("characters", []))
    characters = [c.strip().rstrip("。.;；")
                  for c in _CHAR_SPLIT_RE.split(char_text) if c.strip()]

    hook = "\n".join(_LIST_PREFIX_RE.sub("", h).strip()
                     for h in fields.get("hook", []))
    hook = hook.strip()

    word_estimate = DEFAULT_WORD_ESTIMATE
    for line in fields.get("word_estimate", []):
        digits = "".join(ch for ch in line if ch.isdigit())
        if digits:
            word_estimate = int(digits)
            break

    # era 为单值字段，取首个非空行
    era = ""
    for line in fields.get("era", []):
        line = line.strip()
        if line:
            era = line
            break

    return ChapterOutline(
        num=num or 0,
        title=title,
        events=events,
        characters=characters,
        hook=hook,
        word_estimate=word_estimate,
        era=era,
    )


def _render_chapter(ch: ChapterOutline) -> str:
    lines = [f"## 第{ch.num}章：{ch.title}".rstrip("：")]
    lines.append("")
    lines.append("*   **核心事件**：")
    if ch.events:
        for i, ev in enumerate(ch.events, 1):
            lines.append(f"    {i}.  {ev}")
    lines.append(f"*   **出场角色**：{'、'.join(ch.characters)}")
    lines.append(f"*   **章节悬念/钩子**：{ch.hook}")
    lines.append(f"*   **字数预估**：{ch.word_estimate}字")
    if ch.era:
        lines.append(f"*   **时代**：{ch.era}")
    return "\n".join(lines)
