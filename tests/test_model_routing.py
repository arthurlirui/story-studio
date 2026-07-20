"""单元测试：per-agent 模型路由在构造时的分配。

覆盖 Stage 3.1：
- main tier agents（showrunner/world_architect/character_designer/scene_writer）
  → main_model
- light tier agents（editor/continuity_keeper/literary_advisor/title_designer/
  hooker/climax_designer）→ light_model
- agent_models 覆盖优先于 tier 默认
- main_model == light_model 时全部用 main_model
"""
from __future__ import annotations

from pathlib import Path

import pytest


from config import StudioConfig
from orchestrator import StoryOrchestrator


def _build_orch(tmp_path: Path, main_model="main-x", light_model="light-y",
                agent_models=None):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
        main_model=main_model,
        light_model=light_model,
        agent_models=agent_models or {},
    )
    return StoryOrchestrator(cfg, client=object())


class TestTierRouting:
    def test_main_tier_agents_get_main_model(self, tmp_path: Path):
        orch = _build_orch(tmp_path)
        assert orch.showrunner.model == "main-x"
        assert orch.world_architect.model == "main-x"
        assert orch.character_designer.model == "main-x"
        assert orch.scene_writers[0].model == "main-x"

    def test_light_tier_agents_get_light_model(self, tmp_path: Path):
        orch = _build_orch(tmp_path)
        assert orch.editor.model == "light-y"
        assert orch.continuity_keeper.model == "light-y"
        assert orch.literary_advisor.model == "light-y"
        assert orch.title_designer.model == "light-y"
        assert orch.hooker.model == "light-y"
        assert orch.climax_designer.model == "light-y"

    def test_unified_model_when_main_equals_light(self, tmp_path: Path):
        orch = _build_orch(tmp_path, main_model="same", light_model="same")
        # 所有 agent 都应用 same
        for agent in orch.agents.values():
            assert agent.model == "same"
        for sw in orch.scene_writers:
            assert sw.model == "same"


class TestAgentModelsOverride:
    def test_override_main_tier(self, tmp_path: Path):
        orch = _build_orch(tmp_path, agent_models={"showrunner": "custom-sr"})
        assert orch.showrunner.model == "custom-sr"
        # 未覆盖的仍走 tier 默认
        assert orch.world_architect.model == "main-x"

    def test_override_light_tier(self, tmp_path: Path):
        orch = _build_orch(tmp_path, agent_models={"editor": "custom-ed"})
        assert orch.editor.model == "custom-ed"
        assert orch.continuity_keeper.model == "light-y"

    def test_override_scene_writer(self, tmp_path: Path):
        orch = _build_orch(tmp_path, agent_models={"scene_writer": "sw-custom"})
        assert orch.scene_writers[0].model == "sw-custom"

    def test_override_unknown_role_ignored(self, tmp_path: Path):
        """agent_models 里不存在的 role 不影响任何 agent。"""
        orch = _build_orch(tmp_path, agent_models={"nonexistent": "x"})
        assert orch.showrunner.model == "main-x"
        assert orch.editor.model == "light-y"
