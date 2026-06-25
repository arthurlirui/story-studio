#!/usr/bin/env python3
"""
📰 每日短篇小说生成器
用法: python3 daily_novel.py --topic "热点话题" --direction "选题方向" --subdirection "子方向(可选)"
输出: daily_novels/output/YYYY-MM-DD_HHMM_标题.txt
"""
import asyncio, httpx, logging, sys, re, json, argparse, random
from pathlib import Path
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("daily-novel")

API_BASE = "https://ark.cn-beijing.volces.com/api/coding/v3"
API_KEY = "ark-cbb53828-980b-4d51-89c3-215947aa79f1-62bef"
MODEL = "ark-code-latest"

WORKSPACE = Path(__file__).parent
OUTPUT_DIR = WORKSPACE / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load direction library
DIRECTION_LIB = (WORKSPACE.parent / "创作方向_世界观与选题库.md").read_text(encoding="utf-8")

# Beijing timezone
BJ = timezone(timedelta(hours=8))

SYSTEM_PROMPT = """你是一位资深短篇小说作家，专精于根据热点话题快速创作高质量短篇故事。

你的创作流程：
1. 分析热点话题的核心冲突和情感张力
2. 从选题方向中提取最合适的叙事角度
3. 创作一个完整、有深度、适合番茄小说平台的短篇故事

创作规则：
- 字数：10000-30000字（中短篇，适合番茄小说平台单次发布）
- 直接输出小说正文，不要写任何引导语、说明、注释
- 标题格式：一个吸引人的中文标题（10字以内最佳）
- 开头要有钩子，第一段就抓住读者
- 每段不宜过长，适合手机阅读（番茄小说用户习惯）
- 对话用「」引号
- 结尾要有余韵，不一定要大团圆但要有情感落点
- 语言通俗但不低俗，有文学质感但不晦涩
- 人物要有辨识度，对话要有生活气息
- 结合热点但不生硬，让热点成为故事的背景而非主体"""


def select_direction() -> dict:
    """从选题库中随机选择一个创作方向."""
    directions = [
        {"name": "社会众生相", "desc": "现代背景下普通人的生活叙事，呈现人在时代背景下迸发的别样生命力", "subs": ["小城叙事", "底层人物命运", "市井故事"]},
        {"name": "职业众生相", "desc": "以职业为切口，结合职业特性折射背后的人性与社会", "subs": ["传统职人", "玄学职人", "当代冷门职业", "高压决策行业"]},
        {"name": "关爱群体", "desc": "关注残障人士、流浪者、独居老人、异乡打工者等被主流叙事忽略的群体", "subs": []},
        {"name": "亲情羁绊", "desc": "聚焦父母子女、家庭关系，讨论亲情中的温情、和解、遗憾", "subs": ["空巢老人", "留守儿童", "中年困境"]},
        {"name": "地域特色", "desc": "以特定地理空间为背景，呈现地方性知识与生活方式", "subs": ["西北黄土", "西南苗寨", "东北林区", "闽南侨乡", "藏区牧场"]},
        {"name": "日常喜剧", "desc": "用喜剧解构生活，用欢笑讲述故事", "subs": []},
        {"name": "自我成长", "desc": "个体直面伤痛，在经历中学会和自己、过去和解", "subs": []},
        {"name": "文艺青春", "desc": "围绕校园场景，讲述青少年的成长故事", "subs": []},
        {"name": "双向救赎", "desc": "以人与动物、人与自然、人与人等关系为情感纽带，探讨孤独、陪伴与生命意义", "subs": []},
        {"name": "社会派悬疑", "desc": "用犯罪事件做入口，探讨社会制度、人心幽暗与道德灰色地带", "subs": []},
        {"name": "烧脑推理", "desc": "以本格/变格推理为主线的悬疑故事，注重逻辑严密性和叙事反转", "subs": []},
        {"name": "科幻脑洞", "desc": "以科幻、奇幻、脑洞设定为载体，探讨文化、人性、时空与人类命运", "subs": []},
        {"name": "游戏剧情", "desc": "无限流或时空循环等游戏化叙事", "subs": ["无限流", "时空循环"]},
        {"name": "历史文化", "desc": "聚焦某个历史切片，讲述人物经典故事或人物小传", "subs": []},
        {"name": "志怪灵异", "desc": "取材古典志怪，以现代视角重新解读人妖/人鬼关系中的人性寓言", "subs": ["志怪新编", "神话解构", "西方诸神"]},
    ]
    d = random.choice(directions)
    sub = random.choice(d["subs"]) if d["subs"] else ""
    return {"name": d["name"], "desc": d["desc"], "sub": sub}


async def search_hot_topics() -> list:
    """搜索热点话题（fallback，实际由agent完成搜索）."""
    # This is a fallback; the agent should provide topics via --topic
    fallback_topics = [
        {"title": "外卖骑手的一天", "snippet": "平台经济下的劳动者生存现状"},
        {"title": "独居老人的春节", "snippet": "老龄化社会中的孤独与温情"},
        {"title": "城中村拆迁", "snippet": "城市化进程中的个体命运"},
        {"title": "高考放榜夜", "snippet": "千万家庭的悲欢时刻"},
        {"title": "ICU门口的等待", "snippet": "生死边缘的人间百态"},
        {"title": "宠物殡葬师", "snippet": "冷门职业背后的人性温度"},
        {"title": "非遗传承人的困境", "snippet": "传统手艺在现代社会的挣扎"},
        {"title": "北漂十年", "snippet": "异乡人的城市梦与归途"},
        {"title": "AI取代岗位的焦虑", "snippet": "技术变革下的职场危机"},
        {"title": "全职妈妈的困境", "snippet": "被忽视的家庭劳动者"},
    ]
    return fallback_topics


async def write_novel(topic: str, direction: str, subdirection: str = "") -> str:
    """根据热点话题和选题方向创作短篇小说."""
    
    direction_context = f"""## 选题方向
主方向：{direction}
{f"子方向：{subdirection}" if subdirection else ""}

## 选题库参考
{DIRECTION_LIB[:3000]}

## 热点话题
{topic}

## 创作要求
1. 基于以上热点话题，从选题方向切入，创作一篇完整的短篇小说
2. 字数：严格控制在10000-30000字之间，不得少于10000字！这是硬性要求
3. 适合番茄小说平台：开头抓人、段落短小、情感饱满、适合手机阅读
4. 标题要有吸引力（10字以内）
5. 直接输出小说正文，不要写任何引导语、注释或说明
6. 不要写"短篇小说"、"作者："等标签，直接从标题开始
7. 对话用「」引号
8. 结尾要有情感落点
9. 如果字数不足10000字，请扩充情节、增加细节描写和人物对话，确保达到字数要求"""

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": direction_context},
        ],
        "temperature": 0.9,
        "max_tokens": 65536,
    }

    for attempt in range(5):
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(f"{API_BASE}/chat/completions", json=payload, headers=headers)
            if resp.status_code == 429:
                delay = 5 * (2 ** attempt)
                logger.warning(f"Rate limited, retry in {delay}s")
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(5)
    return ""


def extract_title(text: str) -> str:
    """从正文第一行提取标题."""
    first_line = text.strip().split("\n")[0]
    # Remove markdown headers
    first_line = re.sub(r'^#+\s*', '', first_line)
    # Clean up
    first_line = first_line.strip()
    if len(first_line) > 30:
        first_line = first_line[:30]
    # Sanitize for filename
    title = re.sub(r'[\\/:*?"<>|]', '', first_line)
    return title or "未命名"


def save_novel(text: str, topic: str, direction: str) -> Path:
    """保存小说为TXT，清理格式."""
    # Clean markdown artifacts
    clean = text.strip()
    clean = re.sub(r'\*\*', '', clean)
    clean = re.sub(r'\n---\n', '\n\n', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    clean = re.sub(r'[ \t]+$', '', clean, flags=re.MULTILINE)
    clean = clean.strip() + '\n'

    # Generate filename
    now = datetime.now(BJ)
    timestamp = now.strftime("%Y-%m-%d_%H%M")
    title = extract_title(clean)
    filename = f"{timestamp}_{title}.txt"
    path = OUTPUT_DIR / filename

    path.write_text(clean, encoding="utf-8")

    # Also save metadata
    meta_path = OUTPUT_DIR / f"{timestamp}_{title}.meta.json"
    meta = {
        "timestamp": now.isoformat(),
        "topic": topic,
        "direction": direction,
        "title": title,
        "chars": len(clean),
        "filename": filename,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return path


async def main():
    parser = argparse.ArgumentParser(description="每日短篇小说生成器")
    parser.add_argument("--topic", default="", help="热点话题（如已由agent搜索，直接传入）")
    parser.add_argument("--direction", default="", help="选题方向（留空则随机选择）")
    parser.add_argument("--subdirection", default="", help="子方向（可选）")
    parser.add_argument("--skip-search", action="store_true", help="跳过搜索，使用--topic参数")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("📰 每日短篇小说生成器启动")
    now = datetime.now(BJ)
    logger.info(f"时间: {now.strftime('%Y-%m-%d %H:%M')} (北京时间)")

    # Step 1: Get topic
    if args.skip_search and args.topic:
        topic = args.topic
        logger.info(f"使用传入话题: {topic[:100]}")
    elif args.topic:
        topic = args.topic
        logger.info(f"使用传入话题: {topic[:100]}")
    else:
        logger.info("🔍 搜索热点话题...")
        topics = await search_hot_topics()
        if not topics:
            logger.warning("搜索无结果，使用默认话题")
            topics = [{"title": "当代年轻人的生活压力与温情", "snippet": "社会民生"}]
        topic_item = random.choice(topics)
        topic = f"{topic_item['title']} — {topic_item.get('snippet', '')}"
        logger.info(f"选中话题: {topic[:100]}")

    # Step 2: Select direction
    if args.direction:
        direction = {"name": args.direction, "desc": "", "sub": args.subdirection}
    else:
        direction = select_direction()
    logger.info(f"选中方向: {direction['name']} {direction.get('sub', '')}")

    # Step 3: Generate novel
    logger.info("✍️ 开始创作...")
    novel = await write_novel(topic, direction['name'], direction.get('sub', ''))
    if not novel or len(novel) < 500:
        logger.error("生成失败或内容过短")
        sys.exit(1)

    dir_name = direction['name']
    dir_sub = direction.get('sub', '')
    path = save_novel(novel, topic, dir_name)
    logger.info(f"✅ 已保存: {path} ({len(novel)} 字)")

    # Print summary for the agent to report
    title = extract_title(novel)
    print(f"\n📖 标题: {title}")
    print(f"📝 字数: {len(novel)}")
    print(f"📁 文件: {path.name}")
    print(f"🎯 方向: {dir_name} {('/ ' + dir_sub) if dir_sub else ''}")
    print(f"🔥 话题: {topic}")


if __name__ == "__main__":
    asyncio.run(main())
