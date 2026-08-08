"""共享工具函数，避免 orchestrator / coordinator 等模块间的代码重复。"""
from __future__ import annotations

import re

# 章节大纲片段的截断上限
_CH_OUTLINE_LIMIT = 1500


def extract_chapter_outline(outline: str, chapter_num: int) -> str:
    """从大纲中提取指定章节的内容.

    匹配 "第X章" / "## X." / "Chapter X" / 中文数字 "第X章" 四种标记，
    截取到下一个章节标记为止。章号用边界断言，避免 "第1章" 误匹配 "第11章"。

    这是 orchestrator._extract_chapter_outline 和 coordinator.
    _extract_chapter_outline_local 的统一实现，消除两份正则的漂移风险。
    """
    if not outline:
        return ""

    # 中文数字转换（1-999）
    cn_nums = "零一二三四五六七八九"
    def _num_to_cn(n: int) -> str:
        if n <= 0:
            return str(n)
        if n < 10:
            return cn_nums[n]
        if n < 20:
            return "十" + ("" if n == 10 else cn_nums[n - 10])
        if n < 100:
            tens, ones = divmod(n, 10)
            return cn_nums[tens] + "十" + ("" if ones == 0 else cn_nums[ones])
        if n < 1000:
            hundreds, rest = divmod(n, 100)
            head = cn_nums[hundreds] + "百"
            if rest == 0:
                return head
            if rest < 10:
                return head + "零" + cn_nums[rest]
            return head + _num_to_cn(rest)
        return str(n)

    cn = _num_to_cn(chapter_num)
    candidates = [
        rf'第\s*{chapter_num}\s*章',
        rf'##\s*{chapter_num}\s*[\.\、]',
        rf'Chapter\s*{chapter_num}\b',
        rf'第\s*{cn}\s*章',
    ]
    # 下一章节标记的统一正则（数字或中文数字），支持 "## 第N章" 形式
    next_pat = re.compile(
        r'\n(?:##\s*)?第\s*\d+\s*章'
        r'|\n##\s*\d+\s*[\.\、]'
        r'|\n##\s*第\s*[一二三四五六七八九十]+\s*章'
        r'|\nChapter\s*\d+\b'
        r'|\n第\s*[一二三四五六七八九十]+\s*章'
    )

    for pat in candidates:
        m = re.search(pat, outline)
        if not m:
            continue
        start = m.start()
        rest = outline[start:]
        nxt = next_pat.search(rest[1:])  # 跳过开头的本章节标记
        end = (1 + nxt.start()) if nxt else len(rest)
        return rest[:end].strip()[:_CH_OUTLINE_LIMIT]
    return ""
