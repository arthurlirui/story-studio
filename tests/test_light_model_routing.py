"""单元测试：meta 任务（章节标题/简介/封面 brief）路由到 light_model，
正文润色/连续性/终审仍用 main_model。

用 RecordingLLMClient 记录每次 chat 收到的 model 参数，按 prompt 关键词
分类断言：meta 调用用 light_model，核心创作调用用 main_model。

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 驱动。
"""
from __future__ import annotations

import asyncio
import json
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


class RecordingLLMClient:
    """记录每次 chat 的 (prompt, model)，按 prompt 关键词返回固定响应。"""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []  # (prompt, model)

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        prompt = messages[-1]["content"] if messages else ""
        self.calls.append((prompt, model))
        return self._respond(prompt)

    def _respond(self, prompt: str) -> str:
        if "最后一轮全文润色" in prompt:
            return "# 第 1 章 觉醒\n\n陈风睁开眼。\n"
        if "最终连续性检查" in prompt:
            return "连续性检查通过。"
        if "终审" in prompt:
            return "VERDICT: PASS\n\n作品达到交付标准。"
        if "为以下每一章设计" in prompt and "章节标题" in prompt:
            return "第1章：觉醒\n"
        if "内容简介" in prompt and "500 字" in prompt:
            return "陈风在乱世中觉醒，直面宿命之敌。"
        if "封面设计师" in prompt and "JSON" in prompt:
            return json.dumps({
                "title": "x", "subtitle": "", "author": "x",
                "genre": "wuxia", "mood": "epic", "core_visual": "sword",
                "composition": "portrait", "palette": "ink",
                "positive_prompt": "Book cover, wuxia, sword, no readable text",
            }, ensure_ascii=False)
        return "（RecordingLLM 兜底）"


@pytest.fixture
def orch(tmp_path):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        main_model="main-model-x",
        light_model="light-model-y",
    )
    client = RecordingLLMClient()
    o = StoryOrchestrator(cfg, client=client)
    async def _no_pause():
        return None
    o._rate_limit_pause = _no_pause
    o.project_name = "测试小说"
    o.knowledge.save_chapter(1, "# 第1章\n\n正文。\n", "scene_writer")
    return o


def _classify(prompt: str) -> str:
    """根据 prompt 关键词归类为 meta / core。"""
    if "最后一轮全文润色" in prompt:
        return "core_edit"
    if "最终连续性检查" in prompt:
        return "core_continuity"
    if "终审" in prompt:
        return "core_review"
    if "为以下每一章设计" in prompt and "章节标题" in prompt:
        return "meta_titles"
    if "内容简介" in prompt and "500 字" in prompt:
        return "meta_synopsis"
    if "封面设计师" in prompt and "JSON" in prompt:
        return "meta_cover"
    return "other"


async def _meta_calls_use_light_model(orch):
    await orch.phase_complete()
    main = orch.cfg.main_model
    light = orch.cfg.light_model
    assert main != light, "测试需 main_model != light_model 才能区分"

    by_kind: dict[str, list[str]] = {}
    for prompt, model in orch.client.calls:
        kind = _classify(prompt)
        by_kind.setdefault(kind, []).append(model)

    # meta 任务必须用 light_model
    for kind in ("meta_titles", "meta_synopsis", "meta_cover"):
        assert kind in by_kind, f"缺少 {kind} 调用"
        for m in by_kind[kind]:
            assert m == light, f"{kind} 应使用 light_model({light})，实际 {m}"

    # 核心创作调用必须用 main_model
    for kind in ("core_edit", "core_continuity", "core_review"):
        assert kind in by_kind, f"缺少 {kind} 调用"
        for m in by_kind[kind]:
            assert m == main, f"{kind} 应使用 main_model({main})，实际 {m}"


def test_meta_calls_use_light_model(orch):
    _run(_meta_calls_use_light_model(orch))


async def _default_when_light_model_unset(orch):
    # light_model 默认等于 main_model 时，meta 调用也用 main_model（不报错）
    orch.cfg.light_model = orch.cfg.main_model
    await orch.phase_complete()
    # 所有调用都应是 main_model
    for prompt, model in orch.client.calls:
        assert model == orch.cfg.main_model, (
            f"light_model==main_model 时应用 main_model，实际 {model} (prompt: {prompt[:30]!r})"
        )


def test_default_when_light_model_unset(orch):
    _run(_default_when_light_model_unset(orch))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
