#!/usr/bin/env python3
"""
🎭 玉璧之战 — Story Studio 全流程创作脚本

Phase 1: 策划 → Phase 2: 建立 → Phase 3: 大纲 → Phase 4: 写作 → Phase 5: 完稿
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from agents.llm_client import init_client as init_llm
from agents.ollama_client import client as ollama_client
from orchestrator import StoryOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("yubi-battle")

OUTPUT_DIR = Path("/data/openclaw/workspace/story-studio/玉璧之战")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CREATIVE_BRIEF = """
请创作一篇荡气回肠、高潮迭起的短篇历史战争小说《玉璧之战》。

## 历史背景
公元546年，东魏权臣高欢率领倾国之兵十余万围攻西魏边境要塞玉璧城。
守将韦孝宽率数千守军死守不退。高欢用尽一切攻城手段——断水、火攻、地道、土山、冲车、劝降——
韦孝宽一一化解。围攻五十余日，东魏军死伤七万余人，高欢忧愤成疾，被迫撤军。
这是南北朝时期最惨烈的围城战之一，也是高欢一生最大的遗憾——他离胜利只有一步之遥。

## 创作要求

### 主题与基调
- 突出战争的残酷性：尸山血海、断粮断水、瘟疫蔓延
- 英雄人物的宿命感：高欢的"差一点就成功"的遗憾，韦孝宽的"拼尽全力顶着巨大压力"
- 英雄史诗的宏大场面：万军攻城、地道爆破、城墙血战
- 双雄对决：高欢的智谋与执念 vs 韦孝宽的坚韧与智慧

### 结构要求
- 每章必须有高潮和爽点
- 每章结尾要有悬念或钩子
- 节奏：紧张→舒缓→更紧张→高潮→余韵
- 多视角叙事：高欢视角、韦孝宽视角、普通士兵视角交替

### 人物塑造
- 高欢：一代枭雄，智谋过人，但被执念所困。每次以为胜券在握，都被韦孝宽化解
- 韦孝宽：冷静坚韧的守将，用智慧和意志力一次次击退进攻。内心也有恐惧和动摇，但从不表露
- 配角：高欢麾下将领（斛律金、段韶等）、韦孝宽副将、普通士兵、城中百姓

### 写作风格
- 展示不要告诉 (Show, Don't Tell)
- 感官描写丰富（视觉、听觉、嗅觉、触觉）
- 战争场面要有电影感
- 对话精炼有力
- 第三人称有限视角，多POV切换

### 篇幅
- 建议 8-10 章
- 每章 2000-3500 字
- 总字数约 20000-30000 字
"""


async def save_phase_output(phase_name: str, content: str):
    """保存每个阶段的输出."""
    path = OUTPUT_DIR / f"{phase_name}.md"
    path.write_text(content, encoding="utf-8")
    logger.info(f"Saved {phase_name} → {path}")


async def run():
    cfg = load_config()

    # Choose backend
    if cfg.backend == "llm":
        client = init_llm(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)
        logger.info(f"Backend: LLM API ({cfg.main_model})")
    else:
        client = ollama_client
        client.default_model = cfg.main_model
        logger.info(f"Backend: Ollama ({cfg.main_model})")

    orch = StoryOrchestrator(cfg, client=client)
    orch.project_name = "玉璧之战"

    # ── Phase 1: 策划 ──
    logger.info("=" * 60)
    logger.info("PHASE 1: 策划阶段")
    logger.info("=" * 60)
    plan = await orch.phase_planning(CREATIVE_BRIEF)
    await save_phase_output("01_策划", plan)
    logger.info(f"策划完成 ({len(plan)} 字)")

    # ── Phase 2: 建立（世界观 + 角色）──
    logger.info("=" * 60)
    logger.info("PHASE 2: 建立阶段")
    logger.info("=" * 60)
    building = await orch.phase_building()
    await save_phase_output("02_设定", building)
    logger.info(f"设定完成 ({len(building)} 字)")

    # ── Phase 3: 大纲 ──
    logger.info("=" * 60)
    logger.info("PHASE 3: 大纲阶段")
    logger.info("=" * 60)
    outline = await orch.phase_outlining(total_chapters=9)
    await save_phase_output("03_大纲", outline)
    logger.info(f"大纲完成 ({len(outline)} 字)")

    # ── Phase 4: 写作（逐章）──
    logger.info("=" * 60)
    logger.info("PHASE 4: 写作阶段")
    logger.info("=" * 60)

    all_chapters = []
    for ch in range(1, 10):
        logger.info(f"--- 第 {ch} 章 ---")
        result = await orch.phase_writing(chapter_num=ch)
        all_chapters.append(result)
        await save_phase_output(f"04_第{ch}章", result)
        logger.info(f"第 {ch} 章完成 ({len(result)} 字)")

    # ── Phase 5: 完稿 ──
    logger.info("=" * 60)
    logger.info("PHASE 5: 完稿阶段")
    logger.info("=" * 60)

    # 玉璧之战专属终审标准（保持原有评审质量，不降级为通用评审）
    review_criteria = (
        "1. 荡气回肠、高潮迭起\n"
        "2. 每章有高潮和爽点\n"
        "3. 突出战争残酷和英雄宿命感\n"
        "4. 高欢的遗憾感和韦孝宽的坚韧\n"
        "5. 英雄史诗的宏大场面"
    )
    final_result = await orch.phase_complete(review_criteria=review_criteria)
    await save_phase_output("05_完稿", final_result)
    logger.info("完稿完成")

    # Summary
    status = orch.get_status()
    logger.info("=" * 60)
    logger.info("✅ 创作完成！")
    logger.info(f"项目: {status['project']}")
    logger.info(f"章节: {status['chapters_written']}/{status['total_chapters']}")
    logger.info(f"输出目录: {OUTPUT_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())
