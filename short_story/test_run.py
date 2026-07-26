"""Quick test: 生成一篇重生年代短故事"""
import asyncio, sys, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)

# Add parent to path for story-studio imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.llm_client import init_client
from short_story.engine import ShortStoryPipeline, SkillConfigStore

async def main():
    # Init LLM client (same config as story-studio)
    base_url = "https://llmapi.pcl.ac.cn/v1"
    api_key = "sk-dLcQBdtUNpw5vxrSP8HjlXfJGb8nP8uYlpSMpfKKTD8QfbbS"
    model = "DeepSeek-V4-Pro"
    client = init_client(base_url, api_key, model)
    print(f"LLM: {model} @ {base_url}")

    # Init skill store & pipeline
    skill_dir = Path(__file__).parent / "skill_configs"
    output_dir = Path(__file__).parent / "output"
    knowledge_dir = Path(__file__).parent / "knowledge"

    skills = SkillConfigStore(skill_dir)
    pipeline = ShortStoryPipeline(client, skills, knowledge_dir, output_dir)

    # Generate a rebirth-era short story
    result = await pipeline.generate(
        genre="rebirth_era",
        prompt="女主重生回1985年，前世被渣男和闺蜜联手害死，这辈子要踹渣男搞事业，利用先知能力在供销社对面开全县第一家超市。",
        word_count=8000,
    )

    print(f"\n{'='*60}")
    print(f"书名: {result.title}")
    print(f"简介: {result.synopsis}")
    print(f"总字数: {result.total_words}")
    print(f"耗时: {result.generation_time_s:.1f}s")
    print(f"章节数: {len(result.sections)}")
    print(f"\n输出目录: {output_dir}")
    print(f"  - story_plan.json (策划案)")
    print(f"  - story_final.md  (完整故事)")

    # Show first 300 chars of each section
    for s in result.sections:
        preview = s.text[:200].replace("\n"," ").strip() + "..."
        print(f"\n  [{s.title}] ({s.word_count}字)")
        print(f"  {preview}")

if __name__ == "__main__":
    asyncio.run(main())
