"""单元测试：orchestrator._infer_phase_from_disk 的阶段推断。

验证 /next 在 run_state 缺失/陈旧时能从盘上产物正确恢复 phase。
"""
from __future__ import annotations

from pathlib import Path

import pytest


from config import StudioConfig
from orchestrator import StoryOrchestrator


@pytest.fixture
def orch(tmp_path: Path):
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
    )
    return StoryOrchestrator(cfg, client=object())


def test_infer_idle_when_empty(orch: StoryOrchestrator):
    """空 knowledge_dir → idle。"""
    assert orch._infer_phase_from_disk() == "idle"


def test_infer_building_when_world_exists(orch: StoryOrchestrator):
    """有 world 文档但无 outline/chapter → building。"""
    orch.knowledge.save_world("world.md", "世界观设定内容")
    assert orch._infer_phase_from_disk() == "building"


def test_infer_building_when_character_exists(orch: StoryOrchestrator):
    """有角色但无 outline/chapter → building。"""
    orch.knowledge.save_character("主角", "主角设定")
    assert orch._infer_phase_from_disk() == "building"


def test_infer_outlining_when_outline_exists(orch: StoryOrchestrator):
    """有 outline 但无章节 → outlining。"""
    orch.knowledge.save_outline("## 第 1 章\n起\n")
    assert orch._infer_phase_from_disk() == "outlining"


def test_infer_writing_when_chapter_exists(orch: StoryOrchestrator):
    """有章节但无 final → writing。"""
    orch.knowledge.save_outline("## 第 1 章\n起\n")
    orch.knowledge.save_chapter(1, "第一章正文。", author="scene_writer")
    assert orch._infer_phase_from_disk() == "writing"


def test_infer_complete_when_final_exists(orch: StoryOrchestrator):
    """有 final.md → complete（即使有章节）。"""
    orch.knowledge.save_chapter(1, "第一章正文。", author="scene_writer")
    # final.md 写到 output_dir，不是 knowledge_dir —— 检查实际路径
    out_dir = Path(orch.cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "测试_final.md").write_text("完稿", encoding="utf-8")
    # 但 _infer_phase_from_disk 检查的是 knowledge.story_dir/final.md
    (orch.knowledge.story_dir / "final.md").write_text("完稿", encoding="utf-8")
    assert orch._infer_phase_from_disk() == "complete"
