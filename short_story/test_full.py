"""Full generation test: rebirth-era short story, 5 sections, 7500 words"""
import asyncio, sys, logging, time
from pathlib import Path
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.llm_client import init_client
from short_story.engine import ShortStoryPipeline, SkillConfigStore

async def main():
    import yaml
    with open(Path(__file__).parent.parent / "config/settings.yaml") as f:
        s = yaml.safe_load(f)
    base_url = s["llm_base_url"]
    api_key = s["llm_api_key"]
    model = s["main_model"]
    client = init_client(base_url, api_key, model)

    skill_dir = Path(__file__).parent / "skill_configs"
    output_dir = Path(__file__).parent / "output_full"
    knowledge_dir = Path(__file__).parent / "knowledge"
    skills = SkillConfigStore(skill_dir)
    pipeline = ShortStoryPipeline(client, skills, knowledge_dir, output_dir)

    t0 = time.time()
    print(f"\n{'='*60}")
    print("生成: 重生年代短故事 | 7500字 | 5节")
    print(f"{'='*60}")

    result = await pipeline.generate(
        genre="rebirth_era",
        prompt="女主林雪重生回1985年纺织厂宿舍，前世被渣男未婚夫和毒闺蜜联手害死。这辈子她一脚踹渣男、撕闺蜜，利用先知在县城供销社对面开全县第一家自选超市，从80块起家到万元户，让前世仇人跪地求饶。",
        word_count=7500,
    )

    print(f"\n{'='*60}")
    print(f"书名: {result.title}")
    print(f"简介: {result.synopsis}")
    print(f"总字数: {result.total_words}")
    print(f"耗时: {time.time()-t0:.1f}s")
    print(f"章节: {len(result.sections)}节")

    for s in result.sections:
        issues_str = " ⚠️" + ",".join(s.quality_issues) if s.quality_issues else " ✓"
        preview = s.text[:150].replace("\n"," ").strip() + "..."
        print(f"  [{s.title}] {s.word_count}字{issues_str}")
        print(f"  {preview}")

    print(f"\n输出: {output_dir}")
    plan_path = output_dir / "story_plan.json"
    final_path = output_dir / "story_final.md"
    print(f"  策划: {plan_path} ({'存在' if plan_path.exists() else '缺失'})")
    print(f"  全文: {final_path} ({'存在' if final_path.exists() else '缺失'})")

    if final_path.exists():
        print(f"\n全文前800字:\n{result.full_text[:800]}...")

asyncio.run(main())
