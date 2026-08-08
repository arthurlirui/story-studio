"""长篇管线核心逻辑 — 从 run_all.py 提取为结构化 API。

CLI 命令（cli/run.py）直接调用此模块的 async 函数，而非通过 sys.argv hack
篡改全局状态再调 run_all.main()。

阶段：summaries → polish_outline → write_chapters → deai → export
支持断点恢复（.task_progress.json）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from config import load_config
from orchestrator import StoryOrchestrator
from agents.llm_client import LLMClient

logger = logging.getLogger("pipeline-core")

STAGE_ORDER = ["summaries", "polish_outline", "write_chapters", "deai", "export"]


# ============================================================
# TaskProgress — 持久化进度
# ============================================================

class TaskProgress:
    """进度文件: {variant}/knowledge/.task_progress.json"""

    @staticmethod
    def path(vp: Path) -> Path:
        return vp / "knowledge" / ".task_progress.json"

    @staticmethod
    def load(vp: Path) -> dict:
        p = TaskProgress.path(vp)
        if p.exists():
            try:
                return json.loads(p.read_text("utf-8"))
            except Exception:
                pass
        return {}

    @staticmethod
    def save(vp: Path, data: dict) -> None:
        p = TaskProgress.path(vp)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        tmp.rename(p)

    @staticmethod
    def mark_complete(vp: Path, stage: str) -> None:
        d = TaskProgress.load(vp)
        d[stage] = "complete"
        d[f"{stage}_at"] = time.time()
        d.pop(f"{stage}_error", None)
        TaskProgress.save(vp, d)

    @staticmethod
    def mark_failed(vp: Path, stage: str, error: str) -> None:
        d = TaskProgress.load(vp)
        d[stage] = "failed"
        d[f"{stage}_error"] = error[:500]
        d[f"{stage}_at"] = time.time()
        TaskProgress.save(vp, d)


def _count_glob(folder: Path, pattern: str) -> int:
    return len(list(folder.glob(pattern))) if folder.exists() else 0


def stage_status(vp: Path, stage: str, total: int) -> str:
    """complete | in_progress | pending | failed"""
    prog = TaskProgress.load(vp)
    if prog.get(stage) == "complete":
        return "complete"
    if prog.get(stage) == "failed":
        return "failed"

    if stage == "summaries":
        n = _count_glob(vp / "knowledge/story/summaries", "chapter_*.md")
    elif stage == "polish_outline":
        outline = vp / "knowledge/story/outline.md"
        if outline.exists() and _count_glob(vp / "knowledge/story/summaries", "chapter_*.md") > 0:
            return "complete"
        return "pending"
    elif stage == "write_chapters":
        n = _count_glob(vp / "knowledge/story/chapters", "chapter_*.md")
    elif stage == "deai":
        n = _count_glob(vp / "output/polished", "chapter_*.md")
    elif stage == "export":
        return "complete" if (vp / "output/story_final.md").exists() else "pending"
    else:
        return "pending"

    if n >= total:
        return "complete"
    return "in_progress" if n > 0 else "pending"


# ============================================================
# 加载 & 展示
# ============================================================

def list_taskfiles(tasks_dir: Path) -> list[Path]:
    """列出可用 taskfile。"""
    return sorted(tasks_dir.glob("*.json"))


def load_taskfile(name: str, tasks_dir: Path) -> dict | None:
    """加载 taskfile JSON。"""
    if not name.endswith(".json"):
        name += ".json"
    p = tasks_dir / name
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def make_config(vp: Path, task: dict):
    """为 variant 目录构造配置。"""
    cfg = load_config()
    cfg.knowledge_dir = str(vp / "knowledge")
    cfg.output_dir = str(vp / "output")
    cfg.scene_writers = task.get("batch_size", 3)
    cfg.batch_size = task.get("batch_size", 3)
    cfg.max_rounds = 2
    return cfg


# ============================================================
# 阶段实现
# ============================================================

async def run_summaries(orch, name: str, total: int, batch: int) -> bool:
    knowledge = orch.knowledge
    existing = set(knowledge.list_chapters())
    if len(existing) >= total:
        logger.info("    summaries: 全部完成, 跳过")
        return True

    outline = knowledge.load_outline()
    if not outline.strip():
        logger.error("    summaries: 无大纲")
        return False

    logger.info("    summaries: 生成中 (已有 %d 章)", len(existing))

    for ch in range(1, total + 1):
        if ch in existing:
            continue
        try:
            prompt = (
                f"根据大纲，为第{ch}章生成一段100-150字的章节摘要。只输出摘要。\n\n大纲:\n{outline}"
            )
            resp = await orch.client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7, max_tokens=300,
            )
            if resp.strip():
                sdir = Path(orch.cfg.knowledge_dir) / "story" / "summaries"
                sdir.mkdir(parents=True, exist_ok=True)
                (sdir / f"chapter_{ch:03d}.md").write_text(resp.strip(), "utf-8")
                existing.add(ch)
                logger.info("      chapter_%03d OK", ch)
        except Exception as e:
            logger.warning("      chapter_%03d 失败: %s", ch, e)
    return True


async def run_polish_outline(orch, name: str) -> bool:
    knowledge = orch.knowledge
    original = knowledge.load_outline()
    if not original.strip():
        logger.error("    %s: 无大纲", name)
        return False

    ctx = knowledge.build_context(max_chars=orch.cfg.max_context_chars)
    stages = [
        ("标题设计", orch.title_designer, "设计更吸引点击的章节标题（保持章号不变，只优化标题）"),
        ("钩子设计", orch.hooker, "为每一章设计章末钩子方案，指出缺少有效钩子的章节"),
        ("爽点设计", orch.climax_designer, "审视爽点/高潮分布，指出爽点不足的章节并给出强化建议"),
        ("文学顾问", orch.literary_advisor, "分析大纲结构和文学技巧建议"),
    ]
    advice = {}
    for label, agent, task in stages:
        logger.info("    [%s]...", label)
        a = await agent.think(f"{task}\n\n{original}", ctx)
        advice[label] = a

    logger.info("    [综合] showrunner 输出终版...")
    final = await orch.showrunner.think(
        f"整合四份专家建议，输出优化后的最终版章节大纲。\n"
        f"要求：保留核心情节，优化标题、钩子、爽点和结构。\n"
        f"每章包含：章节标题、核心事件、出场角色、章末钩子、字数预估。\n\n"
        f"现有大纲:\n{original}\n\n"
        + "\n\n".join(f"--- {k} ---\n{v}" for k, v in advice.items())
    )
    knowledge.save_outline(final)
    logger.info("    OK (%d字)", len(final))
    return True


async def run_write_chapters(orch, name: str, total: int, batch: int) -> bool:
    orch._set_phase("writing")
    orch.total_chapters = total
    orch._save_state()

    done = orch.knowledge.list_chapters()
    start = (max(done) + 1) if done else 1
    if start > total:
        logger.info("    已全部完成!")
        return True

    logger.info("    从第%d章起, 每批%d章", start, batch)
    for bs in range(start, total + 1, batch):
        cnt = min(batch, total - bs + 1)
        be = bs + cnt - 1
        logger.info("    -- 批次 %d-%d --", bs, be)
        try:
            await orch.phase_writing_batch(bs, cnt)
            orch.current_chapter = be
            orch._save_state()
            logger.info("    批次 %d-%d 完成", bs, be)
        except Exception as e:
            logger.error("    批次失败: %s — 逐章重试", e)
            for ch in range(bs, bs + cnt):
                try:
                    logger.info("    单章: 第%d章", ch)
                    await orch.phase_writing(ch)
                    orch.current_chapter = ch
                    orch._save_state()
                except Exception as e2:
                    logger.error("    第%d章失败: %s", ch, e2)
                    break

    done = orch.knowledge.list_chapters()
    logger.info("    === 写作完毕: %d/%d ===", len(done), total)
    return len(done) >= total


async def run_deai(orch, name: str, total: int, proj_root: Path) -> bool:
    """去AI感润色模块。"""
    logger.info("    === deai 去AI感润色: %s ===", name)

    ch_dir = Path(orch.cfg.knowledge_dir) / "story" / "chapters"
    out_dir = Path(orch.cfg.output_dir) / "polished"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 加载润色模板（优先 v4 → v3 → v2 → v1）
    prompt_path_v4 = proj_root / "polish_prompt_v4.txt"
    prompt_path_v3 = proj_root / "polish_prompt_v3.txt"
    prompt_path_v2 = proj_root / "polish_prompt_v2.txt"
    prompt_path_v1 = proj_root / "polish_prompt.txt"
    for p in (prompt_path_v4, prompt_path_v3, prompt_path_v2, prompt_path_v1):
        if p.exists():
            POLISH_TMPL = p.read_text("utf-8").strip()
            logger.info("    已加载 %s (%d字)", p.name, len(POLISH_TMPL))
            break
    else:
        POLISH_TMPL = "{chapter}"
        logger.warning("    polish_prompt.txt 不存在，走裸润色")

    SYSTEM = POLISH_TMPL

    finished = set()
    for f in out_dir.glob("chapter_*.md"):
        try:
            finished.add(int(f.stem.replace("chapter_", "")))
        except ValueError:
            pass
    if len(finished) >= total:
        logger.info("    ✅ 已全部润色完成 (%d章)", len(finished))
        return True

    pending = sorted(set(range(1, total + 1)) - finished)
    logger.info("    待润色: %d章 | 已完成: %d章", len(pending), len(finished))

    ok = fail = 0
    for ch in pending:
        src = ch_dir / f"chapter_{ch:03d}.md"
        if not src.exists():
            fail += 1
            continue
        original = src.read_text("utf-8")
        if len(original) < 100:
            continue

        user = f"以下是待润色的章节正文，请直接输出润色后的纯净草内容（不要输出任何思考过程、分析、标注）：\n\n{original}"
        output = None
        for attempt in range(3):
            try:
                resp = await orch.client.chat(
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.82, max_tokens=12000,
                )
                text = resp.strip()
                if text and len(text) > 200:
                    output = text
                    break
            except Exception:
                await asyncio.sleep(2)

        if output:
            cleaned = output.strip()
            while "\n\n\n" in cleaned:
                cleaned = cleaned.replace("\n\n\n", "\n\n")
            (out_dir / f"chapter_{ch:03d}.md").write_text(cleaned + "\n", "utf-8")
            (out_dir / f"chapter_{ch:03d}.txt").write_text(cleaned + "\n", "utf-8")
            ok += 1
        else:
            fail += 1

    logger.info("    === deai 完毕: ✅%d  ❌%d ===", ok, fail)
    return fail == 0


async def run_export(orch, name: str) -> bool:
    """导出: 合并所有章节 → story_final.md + story_final.txt"""
    logger.info("    === 导出: %s ===", name)
    ch_dir = Path(orch.cfg.knowledge_dir) / "story" / "chapters"
    out_dir = Path(orch.cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    polished_dir = out_dir / "polished"
    use_dir = polished_dir if polished_dir.exists() and list(polished_dir.glob("chapter_*.md")) else ch_dir
    chapters = sorted(use_dir.glob("chapter_*.md"))
    if not chapters:
        logger.error("    无章节文件")
        return False

    parts = [c.read_text("utf-8") for c in chapters]
    full = "\n\n---\n\n".join(parts)

    (out_dir / "story_final.md").write_text(full, "utf-8")
    (out_dir / "story_final.txt").write_text(full, "utf-8")
    logger.info("    ✅ 导出: %d字", len(full))
    return True


# ============================================================
# 主流程 — 结构化 API（替代 run_all.main 的 argparse 入口）
# ============================================================

async def run_variant(vp: Path, vn: str, task: dict, client: LLMClient,
                      target_stage: str | None = None) -> bool:
    """运行单个 variant 的管线。

    Args:
        vp: variant 目录路径
        vn: variant 名称
        task: taskfile dict
        client: LLMClient 实例
        target_stage: 只跑指定阶段（None = 全部）
    Returns:
        True = 全部阶段成功
    """
    total = task.get("total_chapters", 30)
    batch = task.get("batch_size", 3)
    enabled = [s["name"] for s in task["stages"] if s.get("enabled", True)]

    if target_stage:
        if target_stage in enabled:
            enabled = [target_stage]
        else:
            logger.warning("    阶段 '%s' 未启用", target_stage)
            return False

    cfg = make_config(vp, task)
    orch = StoryOrchestrator(cfg, client=client)

    from pathlib import Path as P
    proj_root = P(__file__).resolve().parent.parent

    logger.info("=" * 50)
    logger.info("📖 %s", vn)

    runners = {
        "summaries": lambda: run_summaries(orch, vn, total, batch),
        "polish_outline": lambda: run_polish_outline(orch, vn),
        "write_chapters": lambda: run_write_chapters(orch, vn, total, batch),
        "deai": lambda: run_deai(orch, vn, total, proj_root),
        "export": lambda: run_export(orch, vn),
    }

    all_ok = True
    for stage in enabled:
        st = stage_status(vp, stage, total)
        if st == "complete":
            logger.info("  ⏭️  %s: 已完成", stage)
            continue

        logger.info("  🚀 %s: 开始 (%s)", stage, st)
        try:
            ok = await runners[stage]()
            if ok:
                TaskProgress.mark_complete(vp, stage)
                logger.info("  ✅ %s: 完成", stage)
            else:
                TaskProgress.mark_failed(vp, stage, "阶段返回失败")
                logger.error("  ❌ %s: 失败", stage)
                all_ok = False
        except Exception as e:
            TaskProgress.mark_failed(vp, stage, str(e))
            logger.error("  ❌ %s: 异常 - %s", stage, e)
            all_ok = False

    # 重置 agent 会话 (避免跨书污染)
    for a in orch.scene_writers:
        a.reset_conversation()
    for a in [orch.showrunner, orch.title_designer, orch.hooker,
              orch.climax_designer, orch.literary_advisor,
              orch.editor, orch.continuity_keeper]:
        a.reset_conversation()

    return all_ok


async def run_pipeline(
    task_name: str,
    *,
    variant: str | None = None,
    stage: str | None = None,
    dry_run: bool = False,
    proj_root: Path | None = None,
) -> None:
    """运行长篇管线（结构化 API，替代 sys.argv hack）。

    Args:
        task_name: taskfile 名（不含 .json）
        variant: 只跑指定 variant（逗号分隔，如 "01,03"）
        stage: 只跑指定 stage
        dry_run: 只预览状态
        proj_root: 项目根目录
    """
    proj_root = proj_root or Path(__file__).resolve().parent.parent
    tasks_dir = proj_root / "tasks"

    task = load_taskfile(task_name, tasks_dir)
    if not task:
        print(f"❌ 找不到任务: {task_name}")
        print(f"   可用: {[f.stem for f in list_taskfiles(tasks_dir)]}")
        return

    base = proj_root / task["base_dir"]
    all_variants = task.get("variant_dirs", [])
    if variant:
        selected = []
        for num in variant.split(","):
            num = num.strip()
            for v in all_variants:
                if v.startswith(num):
                    selected.append(v)
                    break
        variants = selected
    else:
        variants = all_variants

    if dry_run:
        _print_status(task, variants, base)
        return

    logger.info("=" * 60)
    logger.info("🚀 %s | %s本 | %s",
                task["display_name"], len(variants), stage or "全部阶段")
    logger.info("=" * 60)

    cfg0 = load_config()
    client = LLMClient(
        base_url=cfg0.llm_base_url, api_key=cfg0.llm_api_key,
        default_model=cfg0.main_model,
    )
    healthy = await client.check_health()
    logger.info("API: %s", "✅" if healthy else "⚠️ 警告")

    t0 = time.time()
    results = []
    for i, vn in enumerate(variants):
        vp = base / vn
        if not vp.exists():
            logger.warning("[%d/%d] ⚠️  %s 不存在", i + 1, len(variants), vn)
            results.append((vn, False))
            continue
        logger.info("[%d/%d] >>> %s", i + 1, len(variants), vn)
        ok = await run_variant(vp, vn, task, client, stage or None)
        elapsed = (time.time() - t0) / 60
        logger.info("[%d/%d] <<< %s %s  (%.0fmin)", i + 1, len(variants),
                    vn, "✅" if ok else "❌", elapsed)
        results.append((vn, ok))

    await client.aclose()
    elapsed = (time.time() - t0) / 60

    print("")
    print("=" * 60)
    print(f"  📊 完成: {sum(1 for _, ok in results if ok)}/{len(results)}")
    for vn, ok in results:
        print(f"     {'✅' if ok else '❌'} {vn}")
    print(f"  ⏱️  总耗时: {elapsed:.1f}min")
    print("=" * 60)


def _print_status(task: dict, variants: list[str], base: Path) -> None:
    """dry-run 状态预览。"""
    total = task.get("total_chapters", 30)
    enabled = [s["name"] for s in task["stages"] if s.get("enabled", True)]
    print(f"\n{'='*70}")
    print(f"  📋 {task['display_name']}  — 状态预览")
    print(f"{'='*70}")
    for vn in variants:
        vp = base / vn
        if not vp.exists():
            print(f"  {vn:<16s}  ⚠️ 目录不存在")
            continue
        ch_n = _count_glob(vp / "knowledge/story/chapters", "chapter_*.md")
        line = f"  {vn:<16s}"
        for s in enabled:
            st = stage_status(vp, s, total)
            icon = {"complete": "✅", "in_progress": "🔄", "pending": "⬜", "failed": "❌"}[st]
            line += f"  {icon:>4s}"
        line += f"  {ch_n:>3d}/{total}"
        print(line)
