#!/usr/bin/env python3
"""
轮回怪谈·十日长安 — 正文写作启动脚本

已有设定: world/characters/outline (30章)
目标: 从第1章开始批量写作正文，3章一批并行
"""
import asyncio
import logging
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from orchestrator import StoryOrchestrator
from agents.llm_client import init_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("write-changan")


async def main():
    cfg = load_config()
    logger.info("配置加载完成: knowledge_dir=%s, model=%s", cfg.knowledge_dir, cfg.main_model)

    vc = init_client(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)
    orchestrator = StoryOrchestrator(cfg, client=vc)

    # 检查 API
    healthy = await vc.check_health()
    if not healthy:
        logger.warning("⚠️ LLM API 连接异常")
    else:
        logger.info("✅ LLM API 已连接")

    # 推断 phase
    phase = orchestrator._infer_phase_from_disk()
    logger.info("磁盘产物推断 phase=%s", phase)

    if phase == "idle":
        logger.error("未找到已有设定，请先运行 setup_lunhui.py")
        return

    # 确保有 outline → 设为 outlining 然后 writing
    orchestrator._set_phase("writing")
    orchestrator.total_chapters = 30
    orchestrator._save_state()

    # 检查已写章节
    chapters_done = orchestrator.knowledge.list_chapters()
    logger.info("已完成章节: %s", chapters_done if chapters_done else "无")

    total = 30
    batch_size = cfg.batch_size  # 3

    # 从第1章开始，3章一批
    start = 1
    if chapters_done:
        start = max(chapters_done) + 1

    logger.info("开始批量写作: 从第%d章起，每批%d章，共%d章", start, batch_size, total)

    for batch_start in range(start, total + 1, batch_size):
        count = min(batch_size, total - batch_start + 1)
        logger.info("━━━ 批次: 第%d-%d章 (%d章) ━━━", batch_start, batch_start + count - 1, count)

        try:
            result = await orchestrator.phase_writing_batch(batch_start, count)
            logger.info("批次完成: %s", result[:200])

            # 保存状态
            orchestrator.current_chapter = batch_start + count - 1
            orchestrator._save_state()

        except Exception as e:
            logger.error("批次失败 (第%d章): %s", batch_start, e)
            # 尝试单章继续
            for ch in range(batch_start, batch_start + count):
                try:
                    logger.info("尝试单章写作: 第%d章", ch)
                    result = await orchestrator.phase_writing(ch)
                    logger.info("第%d章完成", ch)
                    orchestrator.current_chapter = ch
                    orchestrator._save_state()
                except Exception as e2:
                    logger.error("第%d章失败: %s", ch, e2)
                    break

    # 检查是否全部完成
    chapters_done = orchestrator.knowledge.list_chapters()
    logger.info("━━━ 写作完毕 ━━━")
    logger.info("已完成章节: %d/%d", len(chapters_done), total)
    if len(chapters_done) >= total:
        logger.info("🎉 全部30章写作完成！")
        # 进入终审
        try:
            result = await orchestrator.phase_complete()
            logger.info("终审完成: %s", result[:300])
        except Exception as e:
            logger.error("终审失败: %s", e)

    await vc.aclose()


if __name__ == "__main__":
    asyncio.run(main())
