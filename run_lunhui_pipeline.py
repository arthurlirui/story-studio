#!/usr/bin/env python3
"""轮回怪谈 Pipeline - 大纲润色 + 全正文生成"""
import asyncio, logging, sys, time, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import load_config
from orchestrator import StoryOrchestrator
from agents.llm_client import init_client, LLMClient

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("lunhui-pipeline")

BASE = Path(__file__).parent / "series" / "轮回怪谈" / "variants"
VARIANT_DIRS = [
    "01_十日长安","02_焚书者","03_轮回三国","04_靖康棋局","05_永历不死",
    "06_封神残局","07_山海轮回","08_聊斋十日","09_白蛇轮回","10_敦煌千夜",
]
TOTAL_CHAPTERS = 30
BATCH_SIZE = 3

def make_config(variant_dir):
    cfg = load_config()
    vpath = str(BASE / variant_dir)
    cfg.knowledge_dir = f"{vpath}/knowledge"
    cfg.series_knowledge_dir = str(BASE.parent / "knowledge")
    cfg.output_dir = f"{vpath}/output"
    cfg.scene_writers = BATCH_SIZE
    cfg.batch_size = BATCH_SIZE
    cfg.max_rounds = 2
    cfg.merge_gate_rounds = 1
    return cfg

async def polish_outline(orch, vname):
    logger.info("=== 润色大纲: %s ===", vname)
    knowledge = orch.knowledge
    original = knowledge.load_outline()
    if not original.strip():
        logger.error("  %s: 无大纲，跳过", vname); return
    context = knowledge.build_context(max_chars=orch.cfg.max_context_chars)

    logger.info("  [1/4] 标题设计...")
    await orch._rate_limit_pause()
    title_advice = await orch.title_designer.think(
        f"请为以下章节大纲设计更吸引点击的章节标题（保持章号不变，只优化标题）。\n\n{original}", context)
    orch._log("title_designer", title_advice)

    logger.info("  [2/4] 钩子设计...")
    await orch._rate_limit_pause()
    hook_advice = await orch.hooker.think(
        f"请为以下章节大纲的每一章设计章末钩子方案，并指出哪些章缺少有效钩子。\n\n{original}", context)
    orch._log("hooker", hook_advice)

    logger.info("  [3/4] 爽点设计...")
    await orch._rate_limit_pause()
    climax_advice = await orch.climax_designer.think(
        f"请审视以下章节大纲的爽点/高潮分布，指出爽点不足的章节并给出强化建议。\n\n{original}", context)
    orch._log("climax_designer", climax_advice)

    logger.info("  [4/4] 文学顾问...")
    await orch._rate_limit_pause()
    lit_advice = await orch.literary_advisor.think(
        f"请分析以下章节大纲，给出结构和文学技巧建议。\n\n{original}", context)
    orch._log("literary_advisor", lit_advice)

    logger.info("  综合专家建议，输出终版大纲...")
    await orch._rate_limit_pause()
    final = await orch.showrunner.think(
        f"你已有现有大纲和四份专家建议。请输出优化后的最终版章节大纲。\n"
        f"要求：保留原有核心情节，但整合所有专家建议优化标题、钩子、爽点和结构。\n"
        f"格式：每章包含章节标题、核心事件、出场角色、章末钩子、字数预估。\n\n"
        f"现有大纲:\n{original}\n\n"
        f"标题设计建议:\n{title_advice}\n\n"
        f"钩子设计建议:\n{hook_advice}\n\n"
        f"爽点设计建议:\n{climax_advice}\n\n"
        f"文学建议:\n{lit_advice}")
    orch._log("showrunner", final)
    knowledge.save_outline(final)
    logger.info("  OK %s 大纲润色完成 (%d 字)", vname, len(final))

async def write_all_chapters(orch, vname):
    logger.info("=== 正文写作: %s ===", vname)
    orch._set_phase("writing")
    orch.total_chapters = TOTAL_CHAPTERS
    orch._save_state()
    done = orch.knowledge.list_chapters()
    logger.info("  已完成: %s", done if done else "无")
    start = (max(done) + 1) if done else 1
    if start > TOTAL_CHAPTERS:
        logger.info("  OK %s 已全部完成", vname); return

    logger.info("  从第%d章起，每批%d章", start, BATCH_SIZE)
    for bs in range(start, TOTAL_CHAPTERS + 1, BATCH_SIZE):
        cnt = min(BATCH_SIZE, TOTAL_CHAPTERS - bs + 1)
        be = bs + cnt - 1
        logger.info("  -- 批次: 第%d-%d章 --", bs, be)
        try:
            await orch.phase_writing_batch(bs, cnt)
            logger.info("  批次 %d-%d 完成", bs, be)
            orch.current_chapter = be
            orch._save_state()
        except Exception as e:
            logger.error("  批次失败: %s", e)
            for ch in range(bs, bs + cnt):
                try:
                    logger.info("  单章: 第%d章", ch)
                    await orch.phase_writing(ch)
                    orch.current_chapter = ch
                    orch._save_state()
                except Exception as e2:
                    logger.error("  第%d章失败: %s", ch, e2)
                    break
    done = orch.knowledge.list_chapters()
    logger.info("  === %s 写作完毕: %d/%d ===", vname, len(done), TOTAL_CHAPTERS)

async def run_variant(vdir, phase, client):
    cfg = make_config(vdir)
    orch = StoryOrchestrator(cfg, client=client)
    logger.info("  %s: phase=%s", vdir, orch._infer_phase_from_disk())
    try:
        if phase in ("polish", "all"):
            await polish_outline(orch, vdir)
        if phase in ("write", "all"):
            await write_all_chapters(orch, vdir)
    except Exception as e:
        logger.error("  FAIL %s: %s", vdir, e)
    for a in orch.scene_writers:
        a.reset_conversation()
    for a in [orch.showrunner, orch.title_designer, orch.hooker,
              orch.climax_designer, orch.literary_advisor,
              orch.editor, orch.continuity_keeper]:
        a.reset_conversation()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["polish", "write", "all"], default="all")
    parser.add_argument("--variants", type=str, default="")
    args = parser.parse_args()

    if args.variants:
        selected = []
        for num in args.variants.split(","):
            num = num.strip()
            for v in VARIANT_DIRS:
                if v.startswith(num):
                    selected.append(v); break
        variants = selected
    else:
        variants = VARIANT_DIRS[:]

    logger.info("LUNHUI PIPELINE START | phase=%s | variants=%s", args.phase, ", ".join(variants))
    t0 = time.time()

    cfg0 = load_config()
    client = init_client(cfg0.llm_base_url, cfg0.llm_api_key, cfg0.main_model)
    healthy = await client.check_health()
    logger.info("  API: %s", "OK" if healthy else "WARN")

    for i, vdir in enumerate(variants):
        logger.info("[%d/%d] >>> %s", i+1, len(variants), vdir)
        await run_variant(vdir, args.phase, client)
        elapsed = time.time() - t0
        logger.info("[%d/%d] <<< %s done, elapsed %.0fmin", i+1, len(variants), vdir, elapsed / 60)

    await client.aclose()
    elapsed = time.time() - t0
    logger.info("LUNHUI PIPELINE DONE | total %.1fmin", elapsed / 60)

if __name__ == "__main__":
    asyncio.run(main())
