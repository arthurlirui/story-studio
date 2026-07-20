"""单元测试：per-agent 模型路由。

Stage 3.1 策略：
- main tier：scene_writer / showrunner / world_architect / character_designer → main_model
- light tier：editor / continuity_keeper / title_designer / hooker / climax_designer
              / literary_advisor → light_model

phase_complete 路径里：
- 终审 (showrunner) → main_model
- final edit (editor) / 最终连续性 (continuity_keeper) → light_model
- meta 任务（章节标题/简介/封面 brief，由 showrunner/literary_advisor 担纲）→ light_model

用 RecordingLLMClient 记录每次 chat 收到的 model 参数，按 prompt 关键词
分类断言各调用走对模型。

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 驱动。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


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


@pytest.fixture
def orch_unified_model(tmp_path):
    """light_model == main_model 的 orchestrator（模拟未配置 light 的场景）。"""
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        main_model="main-model-x",
        light_model="main-model-x",
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

    # light tier 任务必须用 light_model：
    # meta（标题/简介/封面）+ editor 润色 + continuity 连续性检查
    light_kinds = ("meta_titles", "meta_synopsis", "meta_cover",
                   "core_edit", "core_continuity")
    for kind in light_kinds:
        assert kind in by_kind, f"缺少 {kind} 调用"
        for m in by_kind[kind]:
            assert m == light, f"{kind} 应使用 light_model({light})，实际 {m}"

    # main tier：终审 (showrunner) 必须用 main_model
    assert "core_review" in by_kind, "缺少 core_review 调用"
    for m in by_kind["core_review"]:
        assert m == main, f"core_review 应使用 main_model({main})，实际 {m}"


def test_meta_calls_use_light_model(orch):
    _run(_meta_calls_use_light_model(orch))


async def _default_when_light_model_unset(orch_unified_model):
    # light_model == main_model 时，所有 tier 都回退到 main_model（不报错）
    orch = orch_unified_model
    await orch.phase_complete()
    # 所有调用都应是 main_model（light 回退到 main）
    for prompt, model in orch.client.calls:
        assert model == orch.cfg.main_model, (
            f"light_model==main_model 时应用 main_model，实际 {model} (prompt: {prompt[:30]!r})"
        )


def test_default_when_light_model_unset(orch_unified_model):
    _run(_default_when_light_model_unset(orch_unified_model))


async def _agent_models_override_takes_priority(tmp_path):
    """agent_models 显式指定某 agent 的模型时，应覆盖 tier 默认。"""
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        main_model="main-model-x",
        light_model="light-model-y",
        agent_models={"editor": "custom-editor-model"},
    )
    client = RecordingLLMClient()
    orch = StoryOrchestrator(cfg, client=client)

    async def _no_pause():
        return None

    orch._rate_limit_pause = _no_pause
    orch.project_name = "测试小说"
    orch.knowledge.save_chapter(1, "# 第1章\n\n正文。\n", "scene_writer")
    await orch.phase_complete()
    # editor 的 final edit 调用应走 custom-editor-model
    found_custom = False
    for prompt, model in orch.client.calls:
        if "最后一轮全文润色" in prompt:
            assert model == "custom-editor-model", (
                f"agent_models 覆盖应优先，实际 {model}"
            )
            found_custom = True
    assert found_custom, "缺少 editor final edit 调用"


def test_agent_models_override_takes_priority(tmp_path):
    _run(_agent_models_override_takes_priority(tmp_path))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
