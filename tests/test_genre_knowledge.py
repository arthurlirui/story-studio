"""单元测试：题材知识库检测与注入（genre knowledge wiring）。

验证：
- _detect_genre：plan 文本含题材关键词时命中对应 slug；未命中/空文本返回 None
- _load_genre_knowledge：存在的 slug 返回内容并按 max_chars 截断；缺失/空 slug 返回 ""
- phase_outlining 集成：plan 命中题材时，Hooker 调用的 prompt/system 注入题材知识；
  未命中时不注入（行为与接入前一致）

用 FakeLLMClient 让 phase_outlining 的所有 think() 调用返回固定文本，
不依赖 pytest-asyncio：用 asyncio.new_event_loop() 驱动。
"""
from __future__ import annotations

import asyncio

import pytest

from config import StudioConfig
from orchestrator import (
    StoryOrchestrator,
    _GENRE_KNOWLEDGE_MAP,
    _GENRE_KNOWLEDGE_ROOT,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeLLMClient:
    """记录每次 chat 调用的 prompt 与 system，返回固定 outline 文本。"""

    def __init__(self, outline: str):
        self.outline = outline
        self.prompts: list[str] = []
        self.systems: list[str] = []

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        self.prompts.append(messages[-1]["content"] if messages else "")
        self.systems.append(system or "")
        return self.outline


OUTLINE = """## 章节大纲

第1章：废柴之名
- 核心事件：主角觉醒

第2章：初露锋芒
- 核心事件：首次战斗
"""


@pytest.fixture
def make_orch(tmp_path):
    """工厂：构造一个用 FakeLLMClient 的 orchestrator，可预置企划书 plan。"""
    def _make(plan: str = "") -> tuple[StoryOrchestrator, FakeLLMClient]:
        cfg = StudioConfig(
            backend="llm",
            llm_api_key="fake",
            knowledge_dir=str(tmp_path / "knowledge"),
            output_dir=str(tmp_path / "output"),
            scene_writers=1,
        )
        client = FakeLLMClient(OUTLINE)
        orch = StoryOrchestrator(cfg, client=client)
        async def _no_pause():
            return None
        orch._rate_limit_pause = _no_pause
        if plan:
            orch.knowledge.save_world("plan", plan)
        return orch, client
    return _make


# ── _detect_genre ──────────────────────────────────────────


def test_detect_urban_high_martial():
    plan = "## 1. 作品类型/基调\n都市高武 / 热血爽文"
    assert StoryOrchestrator._detect_genre(plan) == "urban-high-martial"


def test_detect_short_keyword():
    # 只出现短关键词"高武"也应命中
    assert StoryOrchestrator._detect_genre("高武世界，武道至上") == "urban-high-martial"


def test_detect_ancient_social_drama():
    assert StoryOrchestrator._detect_genre("古风世情，宅斗权谋") == "ancient-social-drama"


def test_detect_no_match():
    assert StoryOrchestrator._detect_genre("西方奇幻，魔法学院与龙") is None


def test_detect_empty_plan():
    assert StoryOrchestrator._detect_genre("") is None


def test_genre_map_keywords_all_have_dirs():
    """映射表中每个 slug 都应有对应的知识库目录（防 typo）。"""
    for slug in set(_GENRE_KNOWLEDGE_MAP.values()):
        path = _GENRE_KNOWLEDGE_ROOT / slug / "world_knowledge.md"
        assert path.exists(), f"题材知识库文件缺失: {path}"


# ── _load_genre_knowledge ──────────────────────────────────


def test_load_existing_genre_knowledge():
    content = StoryOrchestrator._load_genre_knowledge("urban-high-martial")
    assert "都市高武" in content
    assert "钩子设计专章" in content


def test_load_genre_knowledge_truncates():
    content = StoryOrchestrator._load_genre_knowledge("urban-high-martial", max_chars=100)
    assert len(content) == 100


def test_load_missing_slug_returns_empty():
    assert StoryOrchestrator._load_genre_knowledge("no-such-genre") == ""


def test_load_empty_slug_returns_empty():
    assert StoryOrchestrator._load_genre_knowledge("") == ""


# ── phase_outlining 集成：Hooker 注入 ──────────────────────

# phase_outlining 中 think() 调用顺序：
# 0=showrunner(大纲) 1=title_designer 2=hooker 3=climax 4=literary 5=showrunner(终稿)
_HOOKER_CALL_IDX = 2


async def _hooker_receives_genre_knowledge(make_orch):
    orch, client = make_orch(plan="## 1. 作品类型/基调\n都市高武 / 热血爽文")
    await orch.phase_outlining(total_chapters=2)
    hooker_prompt = client.prompts[_HOOKER_CALL_IDX]
    hooker_system = client.systems[_HOOKER_CALL_IDX]
    assert "题材知识库" in hooker_prompt, "命中题材时 Hooker prompt 应声明题材知识库"
    assert "## 题材知识库（urban-high-martial）" in hooker_system, (
        "命中题材时 Hooker system 应注入都市高武知识库"
    )
    assert "钩子设计专章" in hooker_system


def test_hooker_receives_genre_knowledge(make_orch):
    _run(_hooker_receives_genre_knowledge(make_orch))


async def _no_genre_no_injection(make_orch):
    orch, client = make_orch(plan="## 1. 作品类型/基调\n西方奇幻 / 魔法冒险")
    await orch.phase_outlining(total_chapters=2)
    hooker_prompt = client.prompts[_HOOKER_CALL_IDX]
    hooker_system = client.systems[_HOOKER_CALL_IDX]
    assert "题材知识库" not in hooker_prompt, "未命中题材时 prompt 不应提及题材知识库"
    assert "## 题材知识库（" not in hooker_system, "未命中题材时 system 不应注入题材知识"


def test_no_genre_no_injection(make_orch):
    _run(_no_genre_no_injection(make_orch))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
