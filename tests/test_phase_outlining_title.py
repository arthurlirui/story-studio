"""单元测试：phase_outlining 末尾从大纲解析书名并回写 project_name。

验证：
- 大纲含 "## 推荐主标题\n《玉璧之战》 — ..." 时，project_name 被设为 "玉璧之战"
- 大纲无书名号时，project_name 不被覆盖（保持原值或空）
- 已设 project_name 时，不被大纲里的书名覆盖

用 FakeLLMClient 让 phase_outlining 的所有 think() 调用返回固定文本，
不依赖 pytest-asyncio：用 asyncio.new_event_loop() 驱动。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import StudioConfig
from orchestrator import StoryOrchestrator


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeLLMClient:
    """所有 think() 调用都返回同一个 outline 文本，模拟 phase_outlining 链路。"""

    def __init__(self, outline: str):
        self.outline = outline
        self.calls: list[str] = []

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        self.calls.append(messages[-1]["content"] if messages else "")
        return self.outline


@pytest.fixture
def make_orch(tmp_path):
    """工厂：构造一个用 FakeLLMClient(outline) 的 orchestrator。"""
    def _make(outline: str, project_name: str = "") -> StoryOrchestrator:
        cfg = StudioConfig(
            backend="llm",
            llm_api_key="fake",
            knowledge_dir=str(tmp_path / "knowledge"),
            output_dir=str(tmp_path / "output"),
            scene_writers=1,
        )
        client = FakeLLMClient(outline)
        orch = StoryOrchestrator(cfg, client=client)
        async def _no_pause():
            return None
        orch._rate_limit_pause = _no_pause
        if project_name:
            orch.project_name = project_name
        return orch
    return _make


# ── 大纲样本 ──────────────────────────────────────────────

OUTLINE_WITH_RECOMMENDED_TITLE = """## 章节大纲

第1章：废柴之名
- 核心事件：主角觉醒

第2章：初露锋芒
- 核心事件：首次战斗

## 总书名候选
1. 《重生之剑神归来》 — 公式：身份反差
2. 《剑斩九天》 — 公式：直球爽点

## 推荐主标题
《玉璧之战》 — 综合历史厚重感与战争意象

## 章节标题设计
- 第1章：废柴之名（风格：进程式）
"""

OUTLINE_WITHOUT_TITLE = """## 章节大纲

第1章：开场
- 主角登场

第2章：冲突
- 矛盾爆发
"""


# ── 测试 ──────────────────────────────────────────────────


async def _parses_recommended_title(make_orch):
    orch = make_orch(OUTLINE_WITH_RECOMMENDED_TITLE)
    assert orch.project_name == ""
    await orch.phase_outlining(total_chapters=2)
    assert orch.project_name == "玉璧之战", (
        f"应解析推荐主标题，实际: {orch.project_name!r}"
    )


def test_parses_recommended_title(make_orch):
    _run(_parses_recommended_title(make_orch))


async def _no_title_keeps_empty(make_orch):
    orch = make_orch(OUTLINE_WITHOUT_TITLE)
    assert orch.project_name == ""
    await orch.phase_outlining(total_chapters=2)
    # 无书名号：保持空，不被设为 None 或别的
    assert orch.project_name == "", (
        f"无书名时 project_name 应保持空，实际: {orch.project_name!r}"
    )


def test_no_title_keeps_empty(make_orch):
    _run(_no_title_keeps_empty(make_orch))


async def _does_not_overwrite_existing_project_name(make_orch):
    orch = make_orch(OUTLINE_WITH_RECOMMENDED_TITLE, project_name="已设书名")
    assert orch.project_name == "已设书名"
    await orch.phase_outlining(total_chapters=2)
    # 已设值优先，不被大纲里的 "玉璧之战" 覆盖
    assert orch.project_name == "已设书名", (
        f"已设 project_name 不应被覆盖，实际: {orch.project_name!r}"
    )


def test_does_not_overwrite_existing_project_name(make_orch):
    _run(_does_not_overwrite_existing_project_name(make_orch))


async def _falls_back_to_candidate_block(make_orch):
    # 没有"推荐主标题"区块，但有"书名候选"区块
    outline = """## 章节大纲
第1章：开场

## 总书名候选
1. 《剑斩九天》 — 公式：直球爽点
2. 《重生之剑神》 — 公式：身份反差
"""
    orch = make_orch(outline)
    await orch.phase_outlining(total_chapters=1)
    assert orch.project_name == "剑斩九天", (
        f"应回退到书名候选首个，实际: {orch.project_name!r}"
    )


def test_falls_back_to_candidate_block(make_orch):
    _run(_falls_back_to_candidate_block(make_orch))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
