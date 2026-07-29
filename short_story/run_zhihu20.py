#!/usr/bin/env python3
"""知乎短篇批量20篇 — 含 deai 去AI润色"""
import asyncio, json, logging, sys, time, traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
import yaml
from agents.llm_client import init_client
from short_story.engine import ShortStoryPipeline, SkillConfigStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zhihu20")

BASE = Path(__file__).parent.parent
SKILL_DIR = BASE / "short_story" / "skill_configs"
KNOW_DIR = BASE / "short_story" / "knowledge"
OUT_BASE = BASE / "series" / "知乎短篇" / "batch20" / "output"

STORIES = [
    ("01", "horror_rules", "中药铺的用药规则",
     "【知乎盐选悬疑】我继承了爷爷的中药铺，每味药都有'使用禁忌'。直到第一个违反规则的患者在我面前腐烂。手札最后一页写着我自己名字。1万字，第一人称，开篇高能，付费点卡在发现手札最后一页，结尾留钩子。"),
    ("02", "urban_system", "社死系统",
     "【知乎盐选脑洞】电梯放屁到账三千，表演忘词到账两万。我开始故意社死赚钱，直到系统提示下一级需要全城直播出丑。1万字，第一人称，反套路爽文，反转连环，结尾留悬念。"),
    ("03", "fierce_female", "离婚冷静期最后一天",
     "【知乎盐选大女主】忍三年冷暴力，离婚冷静期最后一天穿上被他说显胖的红裙子，把他白月光请来当证人。1万字，第一人称，情绪爆发，爽点密集，反转要大。"),
    ("04", "horror_rules", "物业夜间规则",
     "【知乎盐选规则怪谈】便宜小区发来一叠夜间规则，加班按错电梯按钮，负一层停了。1万字，第一人称，规则逐步揭开，层层反转，结尾悬停。"),
    ("05", "rebirth_era", "重生1997卖BB机",
     "【知乎盐选重生】前世985猝死工位，重生1997撕了志愿表去华强北。1万字，第一人称，年代感强，逆袭线爽，结尾留钩子。"),
    ("06", "modern_romance", "假装怀孕之后",
     "【知乎盐选现实情感】老公回家次数比外卖少，买假孕肚试探。他连夜回来跪下打开了一个笔记本。1万字，第一人称，细节扎心，反转有力，结尾悬停。"),
    ("07", "folk_occult", "殡仪馆守夜人",
     "【知乎盐选民俗志怪】守夜第一晚逝者坐起来递烟说还没死透。薪水高得离谱的原因慢慢揭开了。1万字，第一人称，表面写鬼实际写人，结尾情感升华。"),
    ("08", "fierce_female", "面试官问我结婚计划",
     "【知乎盐选大女主】35岁被裁投上百份简历，每次被问生育计划，最后一次我把病历拍桌上。1万字，第一人称，现实共情+爽点不打折。"),
    ("09", "apocalypse_scifi", "全球断网第180天",
     "【知乎盐选末世】全球通讯瘫痪180天，废墟里看到邻居家灯亮着——三个月前他的尸体被抬走了。1万字，第一人称，悬念持续推进，真相出乎意料。"),
    ("10", "urban_system", "拒绝就变强",
     "【知乎盐选系统爽文】签离职协议时绑定系统：每拒绝不合理要求体质+1。把协议推回去。1万字，第一人称，每次拒绝都有爽点，结尾致命选择。"),
    ("11", "horror_rules", "网约车的第四条规则",
     "【知乎盐选规则怪谈】凌晨叫网约车，司机发来四条乘车规则。第四条只写了一个字就被撤回。1万字，第一人称，密闭空间层层揭示，结尾留悬念。"),
    ("12", "rebirth_era", "重生举报猥亵老师",
     "【知乎盐选重生复仇】前世三女生被体育老师猥亵校方压十年。重生回开学第一天体育老师进了教室，我举手。1万字，第一人称，真实感人，正义被执行，结尾升华。"),
    ("13", "quick_transmig", "穿成恶毒女配后",
     "【知乎盐选快穿】穿成恶毒女配活不过第三章，连夜通知所有反派远离女主保命。全文高能搞笑反套路。1万字，第一人称，逻辑在线结局出人意料。"),
    ("14", "folk_occult", "笔仙写的欠款单",
     "【知乎盐选民俗反转】聚会玩笔仙，笔写出精确到分的数字——和我爸在澳门的赌债一模一样。1万字，第一人称，笔仙是引子，真正反转在人身上。"),
    ("15", "modern_romance", "婚恋APP刷到老公",
     "【知乎盐选婚姻悬疑】老公出差无聊刷婚恋APP，划到他的照片简介写着丧偶。点进聊天框。1万字，第一人称，对话推进，细节扎心，反转连环。"),
    ("16", "xianxia", "修仙宗门变互联网大厂",
     "【知乎盐选仙侠脑洞】闭关千年元婴归来，宗门变旋转玻璃门，弟子穿西装：师尊您本月KPI是度化30个凡人。1万字，第一人称，反讽搞笑，逻辑自洽，结尾出人意料。"),
    ("17", "fierce_female", "婆婆请的月嫂是侦探",
     "【知乎盐选大女主】婆婆嫌我花销大月嫂费都AA，深夜月嫂敲门：小姐，亲子鉴定出来了。1万字，第一人称，家庭悬疑+大女主复仇，反转连环。"),
    ("18", "horror_rules", "写字楼电梯第13人",
     "【知乎盐选悬疑恐怖】写字楼电梯限载12人，但我总看到13个肩膀。监控回放里没有第13人。1万字，第一人称，日常场景反常化，层层反转。"),
    ("19", "urban_system", "删除的朋友圈被打印寄回家",
     "【知乎盐选都市悬疑】每次删掉朋友圈内容，第二天出现在家门口快递里。发件人地址是我自己的公寓。1万字，第一人称，悬念步步紧逼，真相颠覆认知。"),
    ("20", "folk_occult", "全家福里多了一个人",
     "【知乎盐选民俗志怪】每年全家福多一个人影，今年那个人影站我身后。翻开老相册发现每一张都有它。1万字，第一人称，表面民俗内核情感，结尾升华。"),
]


async def main():
    # 1. 加载配置
    config_path = BASE / "config" / "settings.yaml"
    with open(config_path) as f:
        s = yaml.safe_load(f)

    # 2. 初始化 LLM client 和 SkillConfigStore
    client = init_client(s["llm_base_url"], s["llm_api_key"], s["main_model"])
    skills = SkillConfigStore(SKILL_DIR)

    # 3. 确保输出目录存在
    OUT_BASE.mkdir(parents=True, exist_ok=True)

    total_start = time.time()
    success = 0
    fail = 0
    results_list = []

    for i, (sid, genre, title_idea, prompt) in enumerate(STORIES):
        out_sub = OUT_BASE / f"z{sid}-{genre}"
        pipe = ShortStoryPipeline(client, skills, KNOW_DIR, out_sub)

        logger.info(f"\n{'='*60}")
        logger.info(f"=== #{i+1}/20: {sid} {title_idea} [{genre}]")
        logger.info(f"=== prompt preview: {prompt[:80]}...")
        logger.info(f"{'='*60}")

        t0 = time.time()
        try:
            result = await pipe.generate(
                genre=genre,
                prompt=prompt,
                word_count=10000,
                enable_deai=True,
            )
            dt = time.time() - t0
            success += 1
            results_list.append({
                "no": i + 1,
                "id": sid,
                "genre": genre,
                "title_idea": title_idea,
                "final_title": result.title,
                "synopsis": result.synopsis,
                "total_words": result.total_words,
                "sections": len(result.sections),
                "time_s": round(dt, 1),
            })
            logger.info(
                f"✅ #{i + 1}: {result.title} — {result.total_words}字 | "
                f"{len(result.sections)}节 | {dt:.0f}s"
            )
        except Exception as e:
            dt = time.time() - t0
            fail += 1
            logger.error(f"❌ #{i + 1}: {e}")
            traceback.print_exc()
            results_list.append({
                "no": i + 1,
                "id": sid,
                "genre": genre,
                "title_idea": title_idea,
                "final_title": "ERROR",
                "synopsis": str(e)[:200],
                "total_words": 0,
                "sections": 0,
                "time_s": round(dt, 1),
            })

    # 4. 汇总输出
    total_dt = time.time() - total_start
    summary = {
        "task": "zhihu20",
        "time": datetime.now().isoformat(),
        "total": len(STORIES),
        "success": success,
        "fail": fail,
        "total_time_s": round(total_dt, 1),
        "avg_time_s": round(total_dt / len(STORIES), 1),
        "results": results_list,
    }

    summary_path = OUT_BASE / "zhihu20_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"汇总: 成功 {success}/{len(STORIES)}, 失败 {fail}")
    logger.info(f"总耗时: {total_dt:.0f}s ({total_dt/60:.1f}min)")
    logger.info(f"摘要已保存: {summary_path}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())