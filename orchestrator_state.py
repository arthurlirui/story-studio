"""RunState — 单次小说生成运行的可恢复状态。

把 orchestrator 原本只放内存的 phase/total_chapters/project_name 持久化到
{knowledge_dir}/run_state.json，让崩溃后的进程能恢复进度。

conversation_log 不持久化（体积大且非关键），仅持久化进度 + 成本聚合。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# 持久化的 phase 取值（与 orchestrator.phase 一致）
PHASE_IDLE = "idle"
PHASE_RESEARCH = "research"
PHASE_INNOVATE = "innovate"
PHASE_PLANNING = "planning"
PHASE_BUILDING = "building"
PHASE_OUTLINING = "outlining"
PHASE_WRITING = "writing"
PHASE_COMPLETE = "complete"


@dataclass
class RunState:
    """单次运行的可恢复状态。"""
    job_id: str
    project_name: str = ""
    phase: str = PHASE_IDLE
    current_chapter: int = 0
    total_chapters: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    # 成本聚合：{model: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int, "calls": int}}
    cost: dict[str, dict[str, int]] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = time.time()

    def save(self, path: Path) -> None:
        """原子写到 run_state.json。"""
        self.touch()
        # M3-dup 修复：复用 knowledge._atomic_write_text，避免逻辑重复
        from agents.knowledge import _atomic_write_text
        _atomic_write_text(
            path,
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
        )

    @classmethod
    def load(cls, path: Path) -> "RunState | None":
        """从 run_state.json 读取。文件不存在或损坏返回 None。"""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # 兼容旧字段：只取已知字段
            return cls(
                job_id=data.get("job_id", ""),
                project_name=data.get("project_name", ""),
                phase=data.get("phase", PHASE_IDLE),
                current_chapter=int(data.get("current_chapter", 0)),
                total_chapters=int(data.get("total_chapters", 0)),
                created_at=float(data.get("created_at", time.time())),
                updated_at=float(data.get("updated_at", time.time())),
                cost=data.get("cost", {}) or {},
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

    def merge_into_orchestrator(self, orch: Any) -> None:
        """把持久化状态合并到 orchestrator 实例（仅在字段为默认值时覆盖）。

        时序约束：此方法仅在 orchestrator 刚构造完（phase 等字段仍是默认值）
        时调用，StoryOrchestrator.__init__ 末尾即按此约定执行。若在构造后
        手动改过 phase/project_name 等字段再调用本方法，恢复行为会被
        「字段非默认值则跳过」的守卫吞掉，导致状态不加载。
        """
        if self.project_name and not orch.project_name:
            orch.project_name = self.project_name
        if self.phase and orch.phase == PHASE_IDLE:
            orch.phase = self.phase
        if self.total_chapters and not orch.total_chapters:
            orch.total_chapters = self.total_chapters
        if self.current_chapter and not orch.current_chapter:
            orch.current_chapter = self.current_chapter
        # job_id 始终覆盖（orchestrator 新建时会生成新的，但恢复时应沿用旧的）
        if self.job_id:
            orch.job_id = self.job_id
        # cost 始终覆盖（orchestrator 内存里默认空）
        if self.cost:
            orch.run_cost = dict(self.cost)

    def record_usage(self, model: str, usage: dict[str, int] | None) -> None:
        """聚合一次 LLM 调用的 token 用量。usage 为 None 时跳过。"""
        if not usage:
            return
        bucket = self.cost.setdefault(model, {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
        })
        bucket["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
        bucket["completion_tokens"] += int(usage.get("completion_tokens", 0))
        bucket["total_tokens"] += int(usage.get("total_tokens", 0))
        bucket["calls"] += 1

    def cost_summary(self) -> dict[str, Any]:
        """返回可读的成本摘要。"""
        total_calls = sum(b.get("calls", 0) for b in self.cost.values())
        total_tokens = sum(b.get("total_tokens", 0) for b in self.cost.values())
        return {
            "by_model": dict(self.cost),
            "total_calls": total_calls,
            "total_tokens": total_tokens,
        }


def new_job_id() -> str:
    """生成短 job_id（时间戳 + 8 位 uuid）。"""
    return f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
