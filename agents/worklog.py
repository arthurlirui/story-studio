"""WorkLog — 智能体集群工作记录（JSONL append-only）.

每条记录是一次 agent 行动的结构化审计条目。文件位置：
    {knowledge_dir}/story/agent_worklog.jsonl

设计：
- append-only，单 orchestrator 内 asyncio.Lock 串行化写入，避免并发撕裂
- JobRunner 每个 job 独立 knowledge_dir，跨 job 天然隔离，无需文件锁
- 字段固定但容忍缺失（旧条目或异常路径可能不填某些字段）
- 与现有 story/reviews/、story/revisions/ 三重存证互补，互不覆盖

条目字段：
    {
      "ts":          ISO 时间戳,
      "job_id":      任务 ID,
      "phase":       orchestrator 阶段（idle/planning/building/outlining/writing/complete）,
      "chapter":     章节号（int，plan/merge 等非章节动作可为 null）,
      "batch_id":    批次 ID（仅并行批次内的条目有）,
      "agent":       agent 实例名（如 scene_writer_1）,
      "role":        角色名（如 Scene Writer）,
      "action":      write|edit|continuity|review|summary|plan|merge,
      "model":       模型名,
      "usage":       {prompt_tokens, completion_tokens, total_tokens},
      "verdict":     PASS|REVISE|REJECT|null,
      "round":       修订轮次（review 动作有）,
      "excerpt":     ≤200 字摘要,
      "duration_ms": 单次调用耗时,
      "error":       错误信息或 null
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 标准 action 枚举（仅用于文档/校验，不强制）
# M10 修复：补齐 research/innovate/task 三个新增 action
ACTIONS = (
    "write", "edit", "continuity", "review", "summary", "plan", "merge",
    "research", "innovate", "task",
)

# 摘要截断长度
_EXCERPT_LIMIT = 200


class WorkLog:
    """智能体工作记录（JSONL append-only，单进程内并发安全）。"""

    def __init__(self, path: str | Path, job_id: str = ""):
        self.path = Path(path)
        self.job_id = job_id
        self._lock = asyncio.Lock()
        # 确保目录存在（文件本身在首次 append 时创建）
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def append(
        self,
        *,
        phase: str = "",
        chapter: int | None = None,
        batch_id: str | None = None,
        agent: str = "",
        role: str = "",
        action: str,
        model: str = "",
        usage: dict[str, int] | None = None,
        verdict: str | None = None,
        round_n: int | None = None,
        excerpt: str = "",
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """异步追加一条工作记录。"""
        entry: dict[str, Any] = {
            "ts": datetime.now().isoformat(),
            "job_id": self.job_id,
            "phase": phase,
            "chapter": chapter,
            "batch_id": batch_id,
            "agent": agent,
            "role": role,
            "action": action,
            "model": model,
            "usage": usage or {},
            "verdict": verdict,
            "round": round_n,
            "excerpt": (excerpt or "")[:_EXCERPT_LIMIT],
            "duration_ms": duration_ms,
            "error": error,
        }
        line = json.dumps(entry, ensure_ascii=False)
        async with self._lock:
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError as e:
                logger.warning("写入 worklog 失败: %s", e)

    def read_recent(self, n: int = 100) -> list[dict]:
        """读取最近 n 条记录（同步，仅供 REPL 查询）。"""
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            logger.warning("读取 worklog 失败: %s", e)
            return []
        out: list[dict] = []
        for line in lines[-n:] if n > 0 else lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
        return out

    def count(self) -> int:
        """总条目数（快速扫描，不解析）。"""
        if not self.path.exists():
            return 0
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0
