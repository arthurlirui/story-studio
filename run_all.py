#!/usr/bin/env python3
"""
Story Studio — 统一任务入口（argparse 壳）

实际逻辑由 cli/pipeline_core.py 提供，本文件仅保留 argparse 命令行接口
以保持向后兼容。CLI 命令 ``ss run pipeline`` 走同一份核心代码。

用法:
    python run_all.py 轮回怪谈                    # 从断点继续
    python run_all.py 轮回怪谈 --variant 01,02    # 只跑指定
    python run_all.py 轮回怪谈 --stage deai       # 只跑指定阶段
    python run_all.py 轮回怪谈 --dry-run          # 预览状态
    python run_all.py --list                      # 列出可用
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cli.pipeline_core import run_pipeline, list_taskfiles, print_taskfile_list

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run-all")

PROJ_ROOT = Path(__file__).parent


async def main():
    p = argparse.ArgumentParser(description="Story Studio 统一任务入口")
    p.add_argument("taskfile", nargs="?", help="任务文件名 (不带.json)")
    p.add_argument("--variant", "-v", default=None, help="只跑指定 variant (逗号分隔)")
    p.add_argument("--stage", "-s", default=None, help="只跑指定阶段")
    p.add_argument("--dry-run", "-n", action="store_true", help="只预览")
    p.add_argument("--list", "-l", action="store_true", help="列出可用 taskfiles")
    args = p.parse_args()

    if args.list:
        print_taskfile_list(PROJ_ROOT / "tasks")
        return

    if not args.taskfile:
        # --list 已处理；无 taskfile 且无 --list → 打印帮助
        p.print_help()
        return

    await run_pipeline(
        args.taskfile,
        variant=args.variant or None,
        stage=args.stage or None,
        dry_run=args.dry_run,
        proj_root=PROJ_ROOT,
    )


if __name__ == "__main__":
    asyncio.run(main())
