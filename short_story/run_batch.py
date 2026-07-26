
"""Batch 50 short stories — serial generation"""
import asyncio, json, logging, sys, time, traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
import yaml
from agents.llm_client import init_client
from short_story.engine import ShortStoryPipeline, SkillConfigStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch50")

BASE = Path(__file__).parent
OUT_DIR = BASE / "output_full"
SKILL_DIR = BASE / "skill_configs"
KNOW_DIR = BASE / "knowledge"

async def main():
    with open(BASE.parent / "config/settings.yaml") as f:
        s = yaml.safe_load(f)
    client = init_client(s["llm_base_url"], s["llm_api_key"], s["main_model"])
    skills = SkillConfigStore(SKILL_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    genres = (
        ["urban_system"] * 7
        + ["fierce_female"] * 6
        + ["apocalypse_scifi"] * 6
        + ["rebirth_era"] * 5
        + ["horror_rules"] * 5
        + ["xianxia"] * 4
        + ["folk_occult"] * 4
        + ["modern_romance"] * 3
        + ["ancient_palace"] * 3
        + ["quick_transmig"] * 2
        + ["farming_business"] * 2
        + ["history_kingdom", "urban_martial", "cute_baby"]
    )

    from short_story.trend_scout import TrendScout

    logger.info("Scouting trends...")
    scout = TrendScout()
    search = await scout.search_all_platforms()

    total_start = time.time()
    success = 0
    fail = 0
    results_list = []

    for i, genre in enumerate(genres):
        label = f"{i+1:02d}"
        out_sub = OUT_DIR / f"{label}-{genre}"
        pipeline = ShortStoryPipeline(client, skills, KNOW_DIR, out_sub)

        logger.info("=== #%d/%d: %s ===", i + 1, len(genres), genre)
        t0 = time.time()
        try:
            result = await pipeline.generate(
                genre=genre,
                prompt=f"创作一篇{genre}品类的番茄短故事，基于热榜趋势创新，字数约6000-8000字，要有新鲜独特的世界设定和人物塑造，开篇出钩子，结尾留信息缺口。",
                word_count=8000,
            )
            dt = time.time() - t0
            success += 1
            results_list.append({
                "no": i + 1,
                "genre": genre,
                "title": result.title,
                "synopsis": result.synopsis,
                "total_words": result.total_words,
                "sections": len(result.sections),
                "time_s": round(dt, 1),
            })
            logger.info("OK #%d: %s (%d words, %.0fs)", i + 1, result.title, result.total_words, dt)
        except Exception as e:
            fail += 1
            logger.error("FAIL #%d: %s", i + 1, e)
            traceback.print_exc()
            results_list.append({
                "no": i + 1,
                "genre": genre,
                "title": "ERROR",
                "synopsis": str(e)[:200],
                "total_words": 0,
                "sections": 0,
                "time_s": round(time.time() - t0, 1),
            })

    total_dt = time.time() - total_start
    summary = {
        "task": "batch50",
        "time": datetime.now().isoformat(),
        "total": len(genres),
        "success": success,
        "fail": fail,
        "total_time_s": round(total_dt, 1),
        "results": results_list,
    }
    (OUT_DIR / "batch50_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("DONE: %d/%d success in %.0fs", success, len(genres), total_dt)

if __name__ == "__main__":
    asyncio.run(main())
