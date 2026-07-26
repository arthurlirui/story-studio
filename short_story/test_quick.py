"""Minimal test: 3-section story to avoid OOM"""
import asyncio, sys, logging
from pathlib import Path
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.llm_client import init_client
from short_story.engine import ShortStoryPipeline, SkillConfigStore

async def main():
    base_url = "https://llmapi.pcl.ac.cn/v1"
    api_key = "sk-dLcQBdtUNpw5vxrSP8HjlXfJGb8nP8uYlpSMpfKKTD8QfbbS"
    model = "DeepSeek-V4-Pro"
    client = init_client(base_url, api_key, model)
    skills = SkillConfigStore(Path(__file__).parent / "skill_configs")
    pipeline = ShortStoryPipeline(client, skills, Path(__file__).parent/"knowledge", Path(__file__).parent/"output_quick")
    result = await pipeline.generate(
        genre="rebirth_era",
        prompt="女主重生回1985年被渣男和闺蜜联手害死那天，踹渣男后利用先知搞个体户",
        word_count=4500,
    )
    print(f"\n书名: {result.title}")
    print(f"字数: {result.total_words} 耗时: {result.generation_time_s:.1f}s")
    for s in result.sections:
        print(f"  [{s.title}] {s.word_count}字")
    print(f"\n完整故事:\n{result.full_text[:500]}...")

asyncio.run(main())
