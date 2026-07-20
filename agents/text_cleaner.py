"""
章节文本清洗：md → 干净 txt。纯函数，无 LLM 调用。

融合 daily_novels/pipeline.py 的 save_novel 清洗规则与
fix_tomato_format.py 的更完整规则，并防御性去除段落编号。
"""
from __future__ import annotations

import re

# 章末标记，如 *——第十八章完——*
_CHAPTER_END_MARKER = re.compile(r'\*——[^——]+完——\*')
# 图片占位 ![alt](url)
_IMAGE_PLACEHOLDER = re.compile(r'!\[[^\]]*\]\([^)]*\)')
# 行首段落编号：1. / 1、 / ①②③ / (1) / （1）
_PARA_NUMBER = re.compile(
    r'^\s*(?:\d+[\.、]\s*'
    r'|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑛]+\.?\s*'
    r'|[\(（]\d+[\)）]\s*)',
    re.MULTILINE,
)
# 独占一行的分隔线 --- /***/___
_HRULE = re.compile(r'^[-*_]{3,}\s*$', re.MULTILINE)
# 行首引用前缀 >
_BLOCKQUOTE = re.compile(r'^>\s?', re.MULTILINE)
# 行首 ## 子标题（保留标题文字）
_SUBHEADING = re.compile(r'^#{2,}\s+', re.MULTILINE)
# **加粗** / *斜体*，保留内部文字
_BOLD = re.compile(r'\*\*([^*]+)\*\*')
_ITALIC = re.compile(r'\*([^*]+)\*')
# 3+ 连续换行
_MULTI_NEWLINE = re.compile(r'\n{3,}')
# 行尾空白
_TRAILING_WS = re.compile(r'[ \t]+$', re.MULTILINE)
# 章节首行 H1 标题：# 后不能紧跟另一个 #（否则是 ## 子标题）；
# 末尾换行+正文可选，支持只有标题没有正文的边界情况。
_H1_TITLE = re.compile(r'^#(?![#])[ \t]*(.+?)[ \t]*(?:\n+(.*))?$', re.DOTALL)


def clean_chapter_body(text: str) -> str:
    """清洗单章正文：去 markdown 标记、防御性去段落编号、归一化空行。

    顺序很重要：
    1. 先去图片占位（避免后续正则误伤其内部 []）；
    2. 去章末标记 *——XX完——*（必须在去 *斜体* 之前，否则 * 会被斜体正则吃掉）；
    3. 去 **加粗** / *斜体*（保留内部文字）；
    4. 去引用前缀、分隔线、子标题、段落编号；
    5. 最后归一化空行和去尾空白。
    """
    if not text:
        return ""
    # 1. 去 ![](...) 图片占位
    text = _IMAGE_PLACEHOLDER.sub('', text)
    # 2. 去 *——XX章完——* 章末标记（必须在斜体正则之前）
    text = _CHAPTER_END_MARKER.sub('', text)
    # 3. 去 **加粗** / *斜体*（保留内部文字，与 fix_tomato_format 一致）
    text = _BOLD.sub(r'\1', text)
    text = _ITALIC.sub(r'\1', text)
    # 4. 去 > 引用前缀（保留引用内容作为正文）
    text = _BLOCKQUOTE.sub('', text)
    # 5. 去 --- /***/___ 分隔线（独占一行）
    text = _HRULE.sub('', text)
    # 6. 去 ## 子标题前缀（保留标题文字作为段落起首）
    text = _SUBHEADING.sub('', text)
    # 7. 防御性去段落编号：行首 1. / ①②③ / (1) / （1）
    text = _PARA_NUMBER.sub('', text)
    # 8. 归一化空行：3+ 连续换行 → 2
    text = _MULTI_NEWLINE.sub('\n\n', text)
    # 9. 去每行尾空白
    text = _TRAILING_WS.sub('', text)
    return text.strip()


def strip_existing_title(text: str) -> tuple[str, str]:
    """从章节开头剥离已有的 # H1 标题行，返回 (标题, 正文)。

    无标题、开头是 ## 子标题、或文本为空，则返回 ('', 原文)。
    只有标题没有正文的边界情况返回 (标题, '')。
    """
    if not text:
        return '', ''
    m = _H1_TITLE.match(text)
    if m:
        title = m.group(1).strip()
        body = m.group(2) or ''
        return title, body
    return '', text
