#!/usr/bin/env python3
"""
🎭 Story Studio CLI — 小说剧本创作智能体团队交互界面

用法:
    python main.py                      # 交互模式
    python main.py --new "输入创作需求"  # 一步创建新项目
    python main.py --status              # 查看项目状态
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from orchestrator import StoryOrchestrator
from agents.llm_client import init_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("story-studio")


def banner():
    print("""
╔══════════════════════════════════════════════════╗
║   🎭 Story Studio — 小说剧本创作智能体团队       ║
║   LLM API · 多 Agent 协作 · 3 编剧并行              ║
╚══════════════════════════════════════════════════╝
""")


def help_text():
    print("""
📋 可用命令:

  🎬 创作流程
  /new <需求>          — 开始新项目（输入创作需求）
  /phase               — 查看当前阶段
  /next                — 进入下一阶段
  /write [章节号]       — 写指定章节（默认下一章）
  /review <章节号>      — 审阅章节
  /revise <章节号> <指令> — 指定修改方向后重写

  💬 Agent 对话
  /chat <agent> <消息>  — 直接与某个 Agent 对话
  /agents              — 列出所有 Agent
  /debate <主题>        — 启动团队讨论

  📚 知识管理
  /knowledge           — 查看知识库状态
  /world               — 查看世界观
  /chars               — 查看角色
  /outline             — 查看大纲
  /continuity          — 查看连续性日志

  🔧 系统
  /status              — 系统状态
  /jobs                — 列出所有后台 Job
  /help                — 帮助
  /exit /quit          — 退出

  📝 直接输入文字 = 发送给总策划
""")


async def cmd_new(orchestrator: StoryOrchestrator, request: str) -> str:
    """开始新项目."""
    result = await orchestrator.phase_planning(request)
    return f"\n🎬 **创作企划完成**\n\n{result}\n\n输入 `/next` 进入世界观和角色设定阶段。"


async def main_interactive(orchestrator: StoryOrchestrator):
    """交互模式主循环."""
    banner()
    help_text()

    print(f"🧠 LLM 模型: {orchestrator.cfg.main_model} (主力) / {orchestrator.cfg.light_model} (轻量)")
    print(f"📂 知识库: {orchestrator.cfg.knowledge_dir}")
    print()

    while True:
        try:
            raw = input("🎬 ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        # ── 命令处理 ──
        try:
            if await _dispatch_command(raw, orchestrator):
                break  # /exit /quit 返回 True 退出循环
        except Exception as e:
            # 兜底：任何命令异常都不应杀掉 REPL
            logger.exception("命令执行失败: %s", raw)
            print(f"\n⚠️ 命令出错: {e}\n")


def _parse_int(value: str, what: str) -> int | None:
    """安全解析章节号。失败时打印用法并返回 None（不抛 ValueError）。"""
    try:
        return int(value)
    except (ValueError, TypeError):
        print(f"⚠️ 无效的{what}: {value!r}（应为整数）")
        return None


async def _dispatch_command(raw: str, orchestrator: StoryOrchestrator) -> bool:
    """处理单条 REPL 命令（异步）。返回 True 表示应退出 REPL（/exit /quit）。"""
    if raw == "/exit" or raw == "/quit":
        print("👋 再见！")
        return True

    if raw == "/help":
        help_text()
        return False

    if raw == "/status":
        status = orchestrator.get_status()
        print(f"\n📊 项目: {status['project'] or '(未创建)'}")
        print(f"   阶段: {status['phase']}")
        print(f"   章节: {status['chapters_written']}/{status['total_chapters']}")
        print(f"   世界观文档: {len(status['world_docs'])} 个")
        print(f"   角色档案: {len(status['characters'])} 个")
        print(f"   Agent 团队: {len(status['agents'])} 人")
        print()
        return False

    if raw == "/agents":
        print("\n🤖 创作团队:")
        for a in orchestrator.agents.values():
            print(f"  • {a.name} ({a.role}) — {a.description}")
            print(f"    模型: {a.model}")
        print()
        return False

    if raw.startswith("/new "):
        request = raw[5:]
        result = await cmd_new(orchestrator, request)
        print(result)
        return False

    if raw == "/next":
        status = orchestrator.get_status()
        phase = status["phase"]
        # phase 漂移修复：run_state 缺失/陈旧时从盘上产物推断，避免 /next 卡在 idle
        if phase == "idle":
            inferred = orchestrator._infer_phase_from_disk()
            if inferred != "idle":
                phase = inferred
                orchestrator._set_phase(inferred)
                status = orchestrator.get_status()
        if phase == "idle":
            print("\n⏳ 还没有创建项目，先用 /new <需求> 开始。")
        elif phase == "planning":
            print("\n🌍 进入世界观和角色设定阶段...")
            result = await orchestrator.phase_building()
            print(f"\n✅ 设定完成!\n\n{result[:1000]}...\n\n输入 `/next` 进入大纲阶段。")
        elif phase == "building":
            print("\n📋 生成章节大纲中...")
            result = await orchestrator.phase_outlining()
            print(f"\n✅ 大纲完成!\n\n{result[:1000]}...\n\n输入 `/next` 进入写作阶段，或 `/write 1` 写第一章。")
        elif phase == "outlining":
            print(f"\n📖 开始第 {status['current_chapter'] + 1} 章...")
            result = await orchestrator.phase_writing()
            print(f"\n✅ {result[:1000]}...")
        elif phase == "writing":
            chapters = status["chapters_written"]
            total = status["total_chapters"]
            if total and chapters >= total:
                print("\n🏁 所有章节已完成，进入终审...")
                result = await orchestrator.phase_complete()
                print(f"\n✅ {result[:1000]}...")
            else:
                print(f"\n📖 继续写作第 {status['current_chapter'] + 1} 章...")
                result = await orchestrator.phase_writing()
                print(f"\n✅ {result[:1000]}...")
        elif phase == "complete":
            print("\n✅ 项目已完成。用 `/new <需求>` 开始新项目。")
        else:
            print(f"\n当前阶段: {phase}")
        return False

    if raw.startswith("/write"):
        parts = raw.split()
        chapter_num = None
        if len(parts) > 1:
            chapter_num = _parse_int(parts[1], "章节号")
            if chapter_num is None:
                print("用法: /write [章节号]")
                return False
        print(f"\n✍️ 写作中...")
        result = await orchestrator.phase_writing(chapter_num)
        print(f"\n✅ {result[:1500]}...")
        return False

    if raw.startswith("/chat "):
        parts = raw.split(maxsplit=2)
        if len(parts) < 3:
            print("用法: /chat <agent_name> <消息>")
            return False
        agent_name = parts[1]
        message = parts[2]
        print(f"\n💬 对话中 (→ {agent_name})...")
        result = await orchestrator.chat_with_agent(agent_name, message)
        print(f"\n{result}\n")
        return False

    if raw == "/knowledge":
        docs = orchestrator.knowledge.list_world_docs()
        chars = orchestrator.knowledge.list_characters()
        chs = orchestrator.knowledge.list_chapters()
        print(f"\n📚 知识库状态 ({orchestrator.cfg.knowledge_dir})")
        print(f"  世界观文档: {', '.join(docs) if docs else '(空)'}")
        print(f"  角色档案: {', '.join(chars) if chars else '(空)'}")
        print(f"  章节: {', '.join(str(c) for c in chs) if chs else '(空)'}")
        print()
        return False

    if raw == "/world":
        world = orchestrator.knowledge.get_world_summary()
        print(f"\n🌍 世界观\n\n{world[:2000] or '(暂无设定)'}\n")
        return False

    if raw == "/chars":
        chars = orchestrator.knowledge.list_characters()
        if chars:
            print(f"\n👤 角色列表: {', '.join(chars)}\n")
            for c in chars:
                content = orchestrator.knowledge.load_character(c)
                print(content[:300])
                print("---")
        else:
            print("\n👤 暂无角色\n")
        return False

    if raw == "/outline":
        outline = orchestrator.knowledge.load_outline()
        print(f"\n📋 大纲\n\n{outline[:2000] or '(暂无大纲)'}\n")
        return False

    if raw == "/continuity":
        cl = orchestrator.knowledge.load_continuity_log()
        print(f"\n🔍 连续性日志\n\n{cl[:1000] or '(暂无记录)'}\n")
        return False

    if raw == "/phase":
        print(f"\n当前阶段: {orchestrator.phase}\n")
        return False

    if raw.startswith("/revise "):
        parts = raw.split(maxsplit=2)
        if len(parts) < 3:
            print("用法: /revise <章节号> <修改指令>")
            return False
        ch_str = parts[1]
        instruction = parts[2]
        ch = _parse_int(ch_str, "章节号")
        if ch is None:
            return False
        print(f"\n🔄 修订第 {ch} 章...")
        context = orchestrator.knowledge.build_context(ch)
        content = orchestrator.knowledge.load_chapter(ch)
        if not content:
            print(f"第 {ch} 章不存在")
            return False
        revised = await orchestrator.scene_writers[0].think(
            f"请根据以下指令修改第 {ch} 章。\n\n指令: {instruction}\n\n原文:\n{content}",
            context,
        )
        orchestrator.knowledge.save_chapter(ch, revised, "revision")
        print(f"\n✅ 修订完成。\n\n{revised[:1000]}...\n")
        return False

    if raw.startswith("/review"):
        parts = raw.split()
        ch = orchestrator.current_chapter
        if len(parts) > 1:
            parsed = _parse_int(parts[1], "章节号")
            if parsed is None:
                print("用法: /review [章节号]")
                return False
            ch = parsed
        content = orchestrator.knowledge.load_chapter(ch)
        if not content:
            print(f"第 {ch} 章不存在")
            return False
        print(f"\n🔍 审阅第 {ch} 章...")
        review = await orchestrator.showrunner.review(content[:3000])
        print(f"\n{review}\n")
        return False

    if raw.startswith("/debate "):
        topic = raw[8:]
        print(f"\n🗣️ 团队讨论: {topic}\n")
        result = await orchestrator._team_discussion(topic)
        print(result)
        print()
        return False

    if raw == "/jobs":
        # 列出所有后台 Job（需先 --submit 创建过 job，否则提示）
        from jobs import JobRunner
        runner = JobRunner(base_dir="jobs", cfg=orchestrator.cfg)
        jobs = runner.list()
        if not jobs:
            print("\n📭 暂无后台 Job。用 `python main.py --submit \"<需求>\"` 创建。")
        else:
            print(f"\n📋 后台 Job（{len(jobs)} 个）：")
            for j in jobs:
                prog = f"{j.progress[0]}/{j.progress[1]}" if j.progress[1] else "-"
                print(f"  {j.id}  [{j.status}]  phase={j.phase}  progress={prog}  {j.project_name}")
        print()
        return False

    # 默认：发给 Showrunner
    status = orchestrator.get_status()
    if status["phase"] == "idle":
        result = await cmd_new(orchestrator, raw)
        print(result)
    else:
        result = await orchestrator.chat_with_agent("showrunner", raw)
        print(f"\n🎬 {result}\n")
    return False


async def main():
    cfg = load_config()

    # Init LLM client (llmapi.pcl.ac.cn)
    vc = init_client(cfg.llm_base_url, cfg.llm_api_key, cfg.main_model)
    orchestrator = StoryOrchestrator(cfg, client=vc)

    # Check API health
    healthy = await vc.check_health()
    if not healthy:
        print("⚠️  LLM API 连接异常，但将继续运行...")
    else:
        print(f"✅ LLM API 已连接")
        models = await vc.list_models()
        if models:
            model_ids = [m["id"] for m in models[:10]]
            print(f"   可用模型: {', '.join(model_ids)}")

    # Quick command mode
    if len(sys.argv) > 1:
        if sys.argv[1] == "--status":
            status = orchestrator.get_status()
            print(status)
            return
        elif sys.argv[1] == "--new" and len(sys.argv) > 2:
            request = sys.argv[2]
            result = await cmd_new(orchestrator, request)
            print(result)
            return
        elif sys.argv[1] == "--submit" and len(sys.argv) > 2:
            # 提交后台 Job
            from jobs import JobRunner
            runner = JobRunner(base_dir="jobs", cfg=cfg)
            brief = sys.argv[2]
            project_name = sys.argv[3] if len(sys.argv) > 3 else ""
            job_id = await runner.submit(brief, project_name=project_name)
            print(f"✅ 已提交后台 Job: {job_id}")
            print(f"   用 `python main.py --job {job_id}` 查看状态，`--job-cancel {job_id}` 取消")
            return
        elif sys.argv[1] == "--jobs":
            from jobs import JobRunner
            runner = JobRunner(base_dir="jobs", cfg=cfg)
            jobs = runner.list()
            if not jobs:
                print("📭 暂无后台 Job。")
            else:
                for j in jobs:
                    prog = f"{j.progress[0]}/{j.progress[1]}" if j.progress[1] else "-"
                    print(f"{j.id}  [{j.status}]  phase={j.phase}  progress={prog}  {j.project_name}")
            return
        elif sys.argv[1] == "--job" and len(sys.argv) > 2:
            from jobs import JobRunner
            runner = JobRunner(base_dir="jobs", cfg=cfg)
            job = runner.get(sys.argv[2])
            if job is None:
                print(f"❌ Job {sys.argv[2]} 不存在")
            else:
                print(job.to_dict())
            return
        elif sys.argv[1] == "--job-cancel" and len(sys.argv) > 2:
            from jobs import JobRunner
            runner = JobRunner(base_dir="jobs", cfg=cfg)
            ok = await runner.cancel(sys.argv[2])
            print(f"✅ 已取消 {sys.argv[2]}" if ok else f"❌ 取消失败（job 不存在或已结束）")
            return
        else:
            print(f"未知参数: {sys.argv[1]}")
            print("用法: python main.py [--new '<需求>' | --status | "
                  "--submit '<需求>' [项目名] | --jobs | --job <id> | --job-cancel <id]")

    await main_interactive(orchestrator)


if __name__ == "__main__":
    asyncio.run(main())
