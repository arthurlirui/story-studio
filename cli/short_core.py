"""短篇管线核心逻辑 — 从 run_short.py 提取为结构化 API。

CLI 命令（cli/run.py）直接调用此模块的 async 函数，而非通过 sys.argv hack。

阶段：plan → write → deai
支持断点恢复（.task_progress.json）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from config import load_config
from agents.llm_client import LLMClient
from short_story.engine import ShortStoryPipeline, SkillConfigStore

logger = logging.getLogger("short-core")

STAGE_ORDER = ["plan", "write", "deai"]


class TaskProgress:
    """进度文件: {output_dir}/.task_progress.json"""

    @staticmethod
    def path(out_dir: Path) -> Path:
        return out_dir / ".task_progress.json"

    @staticmethod
    def load(out_dir: Path) -> dict:
        p = TaskProgress.path(out_dir)
        if p.exists():
            try:
                return json.loads(p.read_text("utf-8"))
            except Exception:
                pass
        return {"completed_stages": []}

    @staticmethod
    def save(out_dir: Path, data: dict):
        TaskProgress.path(out_dir).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )


async def run_stage(pipe: ShortStoryPipeline, task: dict, stage: str, out_dir: Path) -> bool:
    """运行单个阶段"""
    word_count = task.get("word_count", 10000)

    if stage == "plan":
        logger.info("  📋 策划中...")
        plan = await pipe._phase_plan(
            task["genre"], task["prompt"], word_count,
            task.get("pov", "first_person"),
            task.get("section_target", 1500),
            pipe.skills.load(task["genre"]),
            {},
        )
        (out_dir / "story_plan.json").write_text(
            json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), "utf-8"
        )
        logger.info("  ✅ 策划完成: %s (%d节)", plan.title, len(plan.sections))
        return True

    elif stage == "write":
        plan_path = out_dir / "story_plan.json"
        if not plan_path.exists():
            logger.error("  ❌ story_plan.json 不存在，请先跑 plan 阶段")
            return False
        plan_data = json.loads(plan_path.read_text("utf-8"))
        from short_story.engine import StoryPlan, SectionPlan, WorldviewCard
        wc = plan_data.get("worldview_card", {})
        plan = StoryPlan(
            genre=task["genre"], title=plan_data["title"],
            synopsis=plan_data["synopsis"], word_count=word_count,
            pov=plan_data.get("pov", "first_person"),
            protagonist=plan_data.get("protagonist", {}),
            sections=[SectionPlan(**s) for s in plan_data.get("sections", [])],
            worldview_card=WorldviewCard(**wc),
        )
        logger.info("  ✍️ 写作中...")
        result = await pipe._phase_write(plan, pipe.skills.load(task["genre"]))
        (out_dir / "story_raw.md").write_text(result.full_text, "utf-8")
        logger.info("  ✅ 写作完成: %d字", result.total_words)
        return True

    elif stage == "deai":
        plan_path = out_dir / "story_plan.json"
        raw_path = out_dir / "story_raw.md"
        if not plan_path.exists() or not raw_path.exists():
            logger.error("  ❌ 缺少 story_plan.json 或 story_raw.md")
            return False
        plan_data = json.loads(plan_path.read_text("utf-8"))
        raw_text = raw_path.read_text("utf-8")

        from short_story.engine import StoryPlan, SectionPlan, WorldviewCard, StoryResult, SectionOutput
        wc = plan_data.get("worldview_card", {})
        plan = StoryPlan(
            genre=task["genre"], title=plan_data["title"],
            synopsis=plan_data["synopsis"], word_count=word_count,
            pov=plan_data.get("pov", "first_person"),
            protagonist=plan_data.get("protagonist", {}),
            sections=[SectionPlan(**s) for s in plan_data.get("sections", [])],
            worldview_card=WorldviewCard(**wc),
        )
        sections = []
        parts = raw_text.split("\n## 第")
        for p in parts[1:]:
            lines = p.strip().split("\n", 1)
            title = f"第{lines[0].strip()}"
            body = lines[1].strip() if len(lines) > 1 else ""
            sec_num = int(lines[0].strip().split("节")[0]) if "节" in lines[0] else 0
            wc_s = len(body.replace("\n", "").replace(" ", ""))
            sections.append(SectionOutput(section=sec_num, title=title, text=body, word_count=wc_s))

        dummy_result = StoryResult(
            title=plan.title, synopsis=plan.synopsis,
            full_text=raw_text, sections=sections,
            total_words=len(raw_text.replace("\n", "").replace(" ", "")),
        )
        logger.info("  🪄 去AI感润色中...")
        result = await pipe._phase_deai(dummy_result, plan)
        (out_dir / "story_final.md").write_text(result.full_text, "utf-8")
        logger.info("  ✅ 润色完成: %d字", result.total_words)
        return True

    return False


async def run_short_task(
    task_name: str,
    target_stage: str | None = None,
    dry_run: bool = False,
    proj_root: Path | None = None,
) -> None:
    """运行短篇任务（结构化 API，替代 sys.argv hack）。

    Args:
        task_name: 任务名
        target_stage: 只跑指定阶段
        dry_run: 预览状态
        proj_root: 项目根目录
    """
    proj_root = proj_root or Path(__file__).resolve().parent.parent
    tasks_dir = proj_root / "tasks" / "short"
    skill_dir = proj_root / "short_story" / "skill_configs"
    series_dir = proj_root / "series"

    # 查找任务文件
    task_path = tasks_dir / f"{task_name}.json"
    if not task_path.exists():
        alt_path = series_dir / task_name / "task.json"
        if alt_path.exists():
            task_path = alt_path
        else:
            logger.error("任务不存在: %s", task_name)
            return

    task = json.loads(task_path.read_text("utf-8"))
    out_dir = series_dir / task_name / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    client = LLMClient(
        base_url=cfg.llm_base_url, api_key=cfg.llm_api_key,
        default_model=cfg.main_model,
    )
    skills = SkillConfigStore(skill_dir)
    pipe = ShortStoryPipeline(client, skills, proj_root / "short_story" / "knowledge", out_dir)

    progress = TaskProgress.load(out_dir)
    completed = set(progress.get("completed_stages", []))

    if dry_run:
        print(f"\n📖 {task.get('title_idea', task_name)}")
        print(f"  品类: {task.get('genre')}")
        print(f"  简介: {task.get('synopsis', task.get('prompt', ''))[:100]}")
        print(f"  进度: {', '.join(completed) if completed else '未开始'}")
        return

    # 确定要跑的阶段
    if target_stage:
        stages = [s for s in STAGE_ORDER if s == target_stage]
        if not stages:
            logger.error("未知阶段: %s (可选: %s)", target_stage, ", ".join(STAGE_ORDER))
            return
    else:
        stages = [s for s in STAGE_ORDER if s not in completed]

    if not stages:
        logger.info("✅ 所有阶段已完成")
        return

    logger.info("待跑阶段: %s", stages)

    for stage in stages:
        t0 = time.time()
        try:
            ok = await run_stage(pipe, task, stage, out_dir)
            if ok:
                completed.add(stage)
                progress["completed_stages"] = sorted(completed, key=lambda s: STAGE_ORDER.index(s))
                progress[f"{stage}_time_s"] = round(time.time() - t0, 1)
                TaskProgress.save(out_dir, progress)
            else:
                logger.error("阶段 %s 失败，中断", stage)
                break
        except Exception as e:
            logger.exception("阶段 %s 异常: %s", stage, e)
            break

    try:
        await client.aclose()
    except Exception:
        pass


async def run_short_batch(
    batch_file: str,
    proj_root: Path | None = None,
) -> None:
    """运行批量短篇任务。"""
    import yaml

    proj_root = proj_root or Path(__file__).resolve().parent.parent
    tasks_dir = proj_root / "tasks" / "short"
    series_dir = proj_root / "series"
    skill_dir = proj_root / "short_story" / "skill_configs"

    batch_path = Path(batch_file)
    if not batch_path.exists():
        batch_path = tasks_dir / f"{batch_file}.yaml"
    if not batch_path.exists():
        batch_path = tasks_dir / batch_file
    if not batch_path.exists():
        batch_path = series_dir / batch_file

    if not batch_path.exists():
        logger.error("批量任务文件不存在: %s", batch_file)
        return

    with open(batch_path) as f:
        batch = yaml.safe_load(f) if batch_path.suffix in (".yaml", ".yml") else json.load(f)

    stories = batch.get("stories", [])
    if not stories:
        logger.error("批量任务中没有 stories 定义")
        return

    logger.info("╔══════════╣ 批量任务: %s (%d篇) ╠══════════╗",
                batch_path.stem, len(stories))

    cfg = load_config()
    client = LLMClient(
        base_url=cfg.llm_base_url, api_key=cfg.llm_api_key,
        default_model=cfg.main_model,
    )
    skills = SkillConfigStore(skill_dir)

    out_base = series_dir / batch_path.stem / "output"
    out_base.mkdir(parents=True, exist_ok=True)

    ok = fail = 0
    results = []
    total_start = time.time()

    for i, story in enumerate(stories):
        sid = story.get("id", f"{i+1:02d}")
        genre = story["genre"]
        prompt = story["prompt"]
        title_idea = story.get("title_idea", "")
        word_count = story.get("word_count", 10000)
        enable_deai = story.get("enable_deai", True)

        out_sub = out_base / f"s{sid}-{genre}"
        pipe = ShortStoryPipeline(client, skills, proj_root / "short_story" / "knowledge", out_sub)

        try:
            result = await pipe.generate(
                genre=genre, prompt=prompt, word_count=word_count, enable_deai=enable_deai
            )
            ok += 1
            results.append({
                "no": i + 1, "id": sid, "genre": genre, "title_idea": title_idea,
                "final_title": result.title, "synopsis": result.synopsis,
                "total_words": result.total_words, "sections": len(result.sections),
                "status": "ok",
            })
        except Exception as e:
            fail += 1
            results.append({
                "no": i + 1, "id": sid, "genre": genre, "title_idea": title_idea,
                "status": "error", "error": str(e),
            })

    await client.aclose()

    total_dt = time.time() - total_start
    summary = {
        "batch": batch_path.stem, "total": len(stories),
        "success": ok, "fail": fail, "total_time_s": round(total_dt, 1),
        "results": results,
    }
    (out_base / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), "utf-8"
    )
    logger.info("║  成功: %d  |  失败: %d  |  耗时: %.0fs", ok, fail, total_dt)


def list_short_tasks(proj_root: Path | None = None) -> None:
    """列出可用短篇任务。"""
    proj_root = proj_root or Path(__file__).resolve().parent.parent
    tasks_dir = proj_root / "tasks" / "short"
    series_dir = proj_root / "series"

    print("\n📚 可用短篇任务:\n")
    if tasks_dir.exists():
        for f in sorted(tasks_dir.glob("*.json")):
            try:
                task = json.loads(f.read_text("utf-8"))
                genre = task.get("genre", "?")
                title = task.get("title_idea", f.stem)
                print(f"  {f.stem:30s} [{genre:18s}] {title}")
            except Exception:
                print(f"  {f.stem:30s} (解析失败)")

    if series_dir.exists():
        for task_file in sorted(series_dir.glob("*/task.json")):
            rel = task_file.parent.relative_to(series_dir)
            try:
                task = json.loads(task_file.read_text("utf-8"))
                genre = task.get("genre", "?")
                title = task.get("title_idea", str(rel))
                print(f"  {str(rel):30s} [{genre:18s}] {title}")
            except Exception:
                print(f"  {str(rel):30s} (解析失败)")
    print()
