"""端到端测试：生成一部短篇小说（ShortStoryPipeline 全流程）。

用真实 LLM 跑 plan -> write -> deai，验证修复后的 llm_client 在真实负载下的稳定性，
并产出 story_plan.json / story_final.md 供人工检视。
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config
from agents.llm_client import init_client
from short_story.engine import ShortStoryPipeline, SkillConfigStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


async def main():
    cfg = load_config()
    print(f"endpoint={cfg.llm_base_url}  model={cfg.main_model}")
    client = init_client(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)

    out_dir = Path("output/test_short_story")
    out_dir.mkdir(parents=True, exist_ok=True)
    skills = SkillConfigStore(Path("short_story/skill_configs"))
    pipe = ShortStoryPipeline(client, skills, knowledge_dir=out_dir, output_dir=out_dir)

    genre = "horror_rules"
    prompt = (
        "主角是新入职的夜班便利店店员。店里贴着一张手写规则："
        "'凌晨2点后不要回应收银台下的敲门声'。第一夜他就听到了敲门声。"
        "围绕规则怪谈展开，悬疑烧脑，主角靠冷静推理存活并发现便利店真相。"
    )
    word_count = 3000  # 2 节，控制耗时

    t0 = time.monotonic()
    try:
        result = await pipe.generate(
            genre, prompt, word_count=word_count, enable_deai=True,
        )
    finally:
        await client.aclose()

    elapsed = time.monotonic() - t0
    print("\n" + "=" * 60)
    print(f"✅ 完成  耗时 {elapsed:.1f}s")
    print(f"标题：{result.title}")
    print(f"简介：{result.synopsis}")
    print(f"总字数：{result.total_words}  节数：{len(result.sections)}")
    for s in result.sections:
        issues = f"  ⚠️ {s.quality_issues}" if s.quality_issues else ""
        print(f"  第{s.section}节《{s.title}》 {s.word_count}字{issues}")
    print(f"\n产物：{out_dir/'story_final.md'}")
    print("=" * 60)
    # 打印第一节开头供快速检视
    if result.sections:
        head = result.sections[0].text[:200].replace("\n", " ")
        print(f"开头预览：{head}……")


if __name__ == "__main__":
    asyncio.run(main())
