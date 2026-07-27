#!/usr/bin/env python3
"""
Story Studio — 统一任务入口

从 tasks/*.json 读取任务描述，一键跑完整流程或从中断处继续。
每阶段完成后写入 .task_progress.json，支持断点恢复。

用法:
    python run_all.py 轮回怪谈                    # 从断点继续
    python run_all.py 轮回怪谈 --variant 01,02    # 只跑指定
    python run_all.py 轮回怪谈 --stage deai       # 只跑指定阶段
    python run_all.py 轮回怪谈 --dry-run          # 预览状态
    python run_all.py --list                      # 列出可用
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
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
logger = logging.getLogger("run-all")

PROJ_ROOT = Path(__file__).parent
TASKS_DIR = PROJ_ROOT / "tasks"
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

def list_taskfiles() -> list[Path]:
    return sorted(TASKS_DIR.glob("*.json"))


def load_taskfile(name: str) -> dict | None:
    if not name.endswith(".json"):
        name += ".json"
    p = TASKS_DIR / name
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def print_status(task: dict, sel: list[str] | None = None) -> None:
    base = PROJ_ROOT / task["base_dir"]
    variants = sel or task.get("variant_dirs", [])
    total = task.get("total_chapters", 30)
    enabled = [s["name"] for s in task["stages"] if s.get("enabled", True)]
    sw = max(len(s) for s in enabled)

    print(f"\n{'='*70}")
    print(f"  📋 {task['display_name']}  — 状态预览")
    print(f"{'='*70}")
    hdr = f"  {'Book':<16s}"
    for s in enabled:
        hdr += f"  {s:>{sw}s}"
    hdr += f"  {'Chapters'}"
    print(hdr)
    print(f"  {'-'*16} {'-'*sw} {'-'*(len(enabled)*(sw+2)-sw-1)} {'-'*8}")

    counts = {s: {"complete": 0, "in_progress": 0, "pending": 0, "failed": 0} for s in enabled}
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
            line += f"  {icon:>{sw}s}"
            counts[s][st] += 1
        line += f"  {ch_n:>3d}/{total}"
        print(line)

    print(f"\n  ── 汇总 ──")
    for s in enabled:
        c = counts[s]
        print(f"  {s:>{sw+2}s}: ✅{c['complete']}  🔄{c['in_progress']}  ⬜{c['pending']}  ❌{c['failed']}")


def make_config(vp: Path, task: dict):
    cfg = load_config()
    cfg.knowledge_dir = str(vp / "knowledge")
    cfg.output_dir = str(vp / "output")
    cfg.scene_writers = task.get("batch_size", 3)
    cfg.batch_size = task.get("batch_size", 3)
    cfg.max_rounds = 2
    return cfg


# ============================================================
# 阶段: summaries
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
            resp = await orch._client.chat(
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


# ============================================================
# 阶段: polish_outline (复用 run_lunhui_pipeline.py)
# ============================================================

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
        await orch._rate_limit_pause()
        a = await agent.think(f"{task}\n\n{original}", ctx)
        advice[label] = a

    logger.info("    [综合] showrunner 输出终版...")
    await orch._rate_limit_pause()
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


# ============================================================
# 阶段: write_chapters
# ============================================================

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


# ============================================================
# 阶段: deai — 去AI感润色 (完善版本)
# ============================================================

async def run_deai(orch, name: str, total: int) -> bool:
    """去AI感润色模块 — 基于 polish_qianhang.py 的成熟方案
    
    流程:
    1. 加载 polish_prompt.txt 作为润色标准
    2. 逐章调 LLMClient.chat() 润色
    3. 每章3次重试 + 429指数退避
    4. 输出到 output/polished/
    5. 不改原文，方便对比效果
    """
    logger.info("    === deai 去AI感润色: %s ===", name)

    ch_dir = Path(orch.cfg.knowledge_dir) / "story" / "chapters"
    out_dir = Path(orch.cfg.output_dir) / "polished"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 加载润色模板
    prompt_path = PROJ_ROOT / "polish_prompt.txt"
    if prompt_path.exists():
        POLISH_TMPL = prompt_path.read_text("utf-8").strip()
        logger.info("    已加载 polish_prompt.txt (%d字)", len(POLISH_TMPL))
    else:
        POLISH_TMPL = "{chapter}"
        logger.warning("    polish_prompt.txt 不存在，走裸润色")

    # 系统 prompt
    SYSTEM = (
        "你是中国顶级网络小说编辑，擅长将好故事提升为精妙的网文作品。"
        "文字冷峻克制有张力，用细节和节奏感抓住读者。"
        "精通历史、悬疑、玄幻、言情、军事、医疗等专业题材。"
    )

    # 统计完成章
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
            logger.warning("    ⚠️  ch%03d 原文不存在", ch)
            fail += 1
            continue

        original = src.read_text("utf-8")
        orig_n = len(original)
        if orig_n < 100:
            logger.warning("    ⚠️  ch%03d 太短(%d字)", ch, orig_n)
            continue

        # 构建 prompt
        user = POLISH_TMPL.replace("{chapter}", original)
        logger.info("    ch%03d (%d字)...", ch, orig_n)

        output = None
        last_err = None

        for attempt in range(3):
            try:
                resp = await orch._client.chat(
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.82,
                    max_tokens=6000,
                )
                text = resp.strip()
                if text and len(text) > 200:
                    output = text
                    break
                last_err = f"输出太短({len(text)}字)"
            except Exception as e:
                last_err = str(e)
                if "429" in str(e) or "Rate" in str(e):
                    wait = 5 * (2 ** attempt)
                    logger.warning("    429 限流, 等%ds...", wait)
                    await asyncio.sleep(wait)
                else:
                    await asyncio.sleep(2)

        if output:
            (out_dir / f"chapter_{ch:03d}.md").write_text(output + "\n", "utf-8")
            pct = len(output) * 100 // orig_n if orig_n else 0
            logger.info("      ✅ ch%03d: %d→%d字 (%d%%)", ch, orig_n, len(output), pct)
            ok += 1
        else:
            logger.error("      ❌ ch%03d: %s", ch, last_err or "未知")
            fail += 1

    logger.info("    === deai 完毕: ✅%d  ❌%d ===", ok, fail)
    return fail == 0


# ============================================================
# 阶段: export
# ============================================================

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

    md_path = out_dir / "story_final.md"
    txt_path = out_dir / "story_final.txt"
    md_path.write_text(full, "utf-8")
    txt_path.write_text(full, "utf-8")

    logger.info("    ✅ 导出: %s (%d字)", md_path, len(full))
    return True


# ============================================================
# 主流程
# ============================================================

async def run_variant(vp, vn, task, client, target_stage=None):
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

    logger.info("=" * 50)
    logger.info("📖 %s", vn)

    runners = {
        "summaries": lambda: run_summaries(orch, vn, total, batch),
        "polish_outline": lambda: run_polish_outline(orch, vn),
        "write_chapters": lambda: run_write_chapters(orch, vn, total, batch),
        "deai": lambda: run_deai(orch, vn, total),
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


async def main():
    p = argparse.ArgumentParser(description="Story Studio 统一任务入口")
    p.add_argument("taskfile", nargs="?", help="任务文件名 (不带.json)")
    p.add_argument("--variant", "-v", default="", help="只跑指定 variant (逗号分隔)")
    p.add_argument("--stage", "-s", default="", help="只跑指定阶段")
    p.add_argument("--dry-run", "-n", action="store_true", help="只预览")
    p.add_argument("--list", "-l", action="store_true", help="列出可用 taskfiles")
    args = p.parse_args()

    if args.list:
        files = list_taskfiles()
        if not files:
            print("没有找到 taskfiles (tasks/*.json)")
        else:
            print(f"可用任务 ({len(files)}):")
            for f in files:
                t = json.loads(f.read_text("utf-8"))
                print(f"  {f.stem:20s} — {t.get('display_name', '?')}")
        return

    if not args.taskfile:
        p.print_help()
        return

    task = load_taskfile(args.taskfile)
    if not task:
        print(f"❌ 找不到任务: {args.taskfile}")
        print(f"   可用: {[f.stem for f in list_taskfiles()]}")
        sys.exit(1)

    base = PROJ_ROOT / task["base_dir"]
    all_variants = task.get("variant_dirs", [])
    if args.variant:
        selected = []
        for num in args.variant.split(","):
            num = num.strip()
            for v in all_variants:
                if v.startswith(num):
                    selected.append(v)
                    break
        variants = selected
    else:
        variants = all_variants

    if args.dry_run:
        print_status(task, variants)
        return

    logger.info("=" * 60)
    logger.info("🚀 %s | %s本 | %s",
                task["display_name"],
                len(variants),
                args.stage or "全部阶段")
    logger.info("=" * 60)

    cfg0 = load_config()
    client = init_client(cfg0.llm_base_url, cfg0.llm_api_key, cfg0.main_model)
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
        ok = await run_variant(vp, vn, task, client, args.stage or None)
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


if __name__ == "__main__":
    asyncio.run(main())
