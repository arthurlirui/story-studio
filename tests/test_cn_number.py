"""单元测试：中文数字解析（_cn_to_int / _num_to_cn 互逆性，1-999）。

P2 #6 修复：原实现 _cn_to_int 仅支持 1-99，但 _parse_total_chapters 的正则
允许「百」，导致「第一百章」解析为 None。扩展到 1-999 后验证互逆性。
"""
from __future__ import annotations

from orchestrator import _cn_to_int, StoryOrchestrator


def test_cn_to_int_basic_digits():
    assert _cn_to_int("一") == 1
    assert _cn_to_int("九") == 9
    assert _cn_to_int("十") == 10


def test_cn_to_int_tens():
    assert _cn_to_int("十一") == 11
    assert _cn_to_int("十九") == 19
    assert _cn_to_int("二十") == 20
    assert _cn_to_int("二十一") == 21
    assert _cn_to_int("九十九") == 99


def test_cn_to_int_hundreds():
    assert _cn_to_int("一百") == 100
    assert _cn_to_int("一百零一") == 101
    assert _cn_to_int("一百十") == 110
    assert _cn_to_int("一百二十三") == 123
    assert _cn_to_int("二百") == 200
    assert _cn_to_int("三百零五") == 305
    assert _cn_to_int("九百九十九") == 999


def test_cn_to_int_arabic_passthrough():
    assert _cn_to_int("1") == 1
    assert _cn_to_int("999") == 999


def test_cn_to_int_invalid():
    assert _cn_to_int("") is None
    assert _cn_to_int("abc") is None


def test_num_to_cn_roundtrip_1_to_999():
    """_num_to_cn 与 _cn_to_int 在 1-999 全程互逆。"""
    fails = []
    for n in range(1, 1000):
        cn = StoryOrchestrator._num_to_cn(n)
        back = _cn_to_int(cn)
        if back != n:
            fails.append((n, cn, back))
    assert not fails, f"互逆失败（前 10）: {fails[:10]}"


def test_num_to_cn_specific_forms():
    assert StoryOrchestrator._num_to_cn(1) == "一"
    assert StoryOrchestrator._num_to_cn(10) == "十"
    assert StoryOrchestrator._num_to_cn(11) == "十一"
    assert StoryOrchestrator._num_to_cn(20) == "二十"
    assert StoryOrchestrator._num_to_cn(99) == "九十九"
    assert StoryOrchestrator._num_to_cn(100) == "一百"
    assert StoryOrchestrator._num_to_cn(101) == "一百零一"
    assert StoryOrchestrator._num_to_cn(999) == "九百九十九"
