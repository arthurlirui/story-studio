#!/usr/bin/env python3
"""
📰 每日短篇小说全流程 — 搜索热点 → 选方向 → 写小说 → 输出TXT
作为 cron job 的入口点，由 agent 在隔离 session 中调用
"""
import asyncio, httpx, logging, sys, re, json, random, os, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("daily-pipeline")

API_BASE = "https://ark.cn-beijing.volces.com/api/coding/v3"
API_KEY = "ark-cbb53828-980b-4d51-89c3-215947aa79f1-62bef"
MODEL = "ark-code-latest"

WORKSPACE = Path(__file__).parent
OUTPUT_DIR = WORKSPACE / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BJ = timezone(timedelta(hours=8))

DIRECTION_LIB = (WORKSPACE.parent / "创作方向_世界观与选题库.md").read_text(encoding="utf-8")

# Direction pool for random selection
DIRECTIONS = [
    {"name": "社会众生相", "desc": "普通人的生活叙事，小城叙事、底层人物命运、市井故事"},
    {"name": "职业众生相", "desc": "以职业为切口，折射人性与社会", "sub": ["传统职人", "当代冷门职业", "高压决策行业"]},
    {"name": "关爱群体", "desc": "残障人士、流浪者、独居老人、异乡打工者"},
    {"name": "亲情羁绊", "desc": "父母子女、家庭关系，温情、和解、遗憾"},
    {"name": "地域特色", "desc": "特定地理空间为背景的地方故事"},
    {"name": "日常喜剧", "desc": "用喜剧解构生活，幽默包裹社会洞察"},
    {"name": "自我成长", "desc": "个体直面伤痛，和解与新生"},
    {"name": "文艺青春", "desc": "校园场景，青少年成长，青春的美好与阵痛"},
    {"name": "双向救赎", "desc": "人与动物/自然/人的情感纽带，温暖治愈"},
    {"name": "社会派悬疑", "desc": "犯罪事件切入，探讨社会制度与人心"},
    {"name": "烧脑推理", "desc": "本格/变格推理，精巧设计，逻辑反转"},
    {"name": "科幻脑洞", "desc": "科幻奇幻设定，探讨人性与人类命运"},
    {"name": "游戏剧情", "desc": "无限流、时空循环等游戏化叙事"},
    {"name": "历史文化", "desc": "历史切片，人物小传，现代视角解构"},
    {"name": "志怪灵异", "desc": "志怪新编、神话解构、东西方诸神故事"},
]


async def search_hot_topics() -> list[dict]:
    """Search for current hot topics using web search API."""
    # Try multiple search queries to get diverse topics
    queries = [
        "今日热点新闻 社会民生 2026年6月",
        "最近热门话题 感人故事 社会事件",
        "当下热议 社会现象 人物故事",
    ]
    
    all_results = []
    for query in queries:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://api.bochaai.com/v1/ai/search",
                    params={"query": query, "count": 5},
                    headers={"Authorization": f"Bearer sk-Y2FvQ0VFQ0Q3NDU2NDQ3MTg4OTJjNDk0ZjdhYzA2NTI2NTY0Nzg2Ng"},
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("data", {}).get("webPages", {}).get("value", [])
                    for r in results:
                        all_results.append({
                            "title": r.get("name", ""),
                            "snippet": r.get("snippet", ""),
                            "url": r.get("url", ""),
                        })
        except Exception as e:
            logger.warning(f"Search '{query}' failed: {e}")
    
    return all_results[:15]


def select_direction() -> dict:
    """Select a direction from the library, with some randomness."""
    # Weight towards social/emotional directions for daily short stories
    weights = [3, 2, 2, 3, 2, 1, 3, 2, 2, 1, 1, 1, 1, 1, 1]
    direction = random.choices(DIRECTIONS, weights=weights, k=1)[0]
    
    # If direction has sub-directions, pick one
    sub = ""
    if direction.get("sub"):
        sub = random.choice(direction["sub"])
    
    return {"name": direction["name"], "desc": direction["desc"], "sub": sub}


async def generate_novel(topic: str, direction: dict) -> str:
    """Generate a short novel based on topic and direction."""
    
    sub_info = f"\n子方向：{direction['sub']}" if direction.get('sub') else ""
    
    prompt = f"""请根据以下热点话题和选题方向，创作一篇适合番茄小说平台的短篇小说。

## 热点话题
{topic}

## 选题方向
主方向：{direction['name']} — {direction['desc']}{sub_info}

## 选题库参考
{DIRECTION_LIB[:2500]}

## 创作要求
1. 字数：10000-30000字
2. 适合番茄小说平台：开头抓人、段落短小、情感饱满、手机阅读友好
3. 标题要有吸引力（10字以内），作为正文第一行
4. 直接输出小说正文，不要写任何引导语、注释或说明
5. 不要写"短篇小说"、"作者："等标签，直接从标题开始
6. 对话用「」引号
7. 语言通俗但有文学质感，不晦涩
8. 人物有辨识度，对话有生活气息
9. 结尾要有情感落点，有余韵
10. 热点作为背景融入，不生硬"""

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一位资深短篇小说作家。直接输出小说正文，不要任何引导语或说明。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "max_tokens": 16384,
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


def save_novel(text: str, topic: str, direction: dict) -> Path:
    """Save novel as clean TXT."""
    clean = text.strip()
    clean = re.sub(r'\*\*', '', clean)
    clean = re.sub(r'\n---\n', '\n\n', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    clean = re.sub(r'[ \t]+$', '', clean, flags=re.MULTILINE)
    clean = clean.strip() + '\n'

    now = datetime.now(BJ)
    timestamp = now.strftime("%Y-%m-%d_%H%M")
    
    # Extract title - keep it short for filename
    first_line = clean.split("\n")[0].strip()
    first_line = re.sub(r'^#+\s*', '', first_line)
    raw_title = re.sub(r'[\\/:*?"<>|]', '', first_line) or "未命名"
    # Truncate to 20 chars max for filename
    title = raw_title[:20] if len(raw_title) > 20 else raw_title
    
    filename = f"{timestamp}_{title}.txt"
    path = OUTPUT_DIR / filename
    path.write_text(clean, encoding="utf-8")

    # Metadata
    meta = {
        "timestamp": now.isoformat(),
        "topic": topic,
        "direction": direction["name"],
        "subdirection": direction.get("sub", ""),
        "title": title,
        "chars": len(clean),
        "filename": filename,
    }
    meta_path = OUTPUT_DIR / f"{timestamp}_{title}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return path


def maybe_generate_cover(novel_path: Path, direction: dict) -> dict | None:
    """Optionally generate a cover via ComfyUI. Non-blocking for novel success."""
    if os.environ.get("GENERATE_COVER", "0") not in {"1", "true", "TRUE", "yes", "YES"}:
        return None

    meta_path = novel_path.with_suffix(".meta.json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        cmd = [
            sys.executable,
            str(WORKSPACE.parent / "tools" / "book_cover_comfy.py"),
            "--title", meta.get("title") or novel_path.stem,
            "--subtitle", direction.get("name", ""),
            "--author", os.environ.get("COVER_AUTHOR", "Arthur 著"),
            "--novel-file", str(novel_path),
            "--output-dir", str(WORKSPACE.parent / "output" / "covers"),
        ]
        logger.info("🎨 生成小说封面...")
        proc = subprocess.run(cmd, cwd=str(WORKSPACE.parent), text=True, capture_output=True, timeout=1200)
        if proc.returncode != 0:
            logger.warning(f"封面生成失败: {proc.stderr[-1000:]}")
            meta["cover_error"] = proc.stderr[-2000:] or proc.stdout[-2000:]
        else:
            last = proc.stdout.strip().splitlines()[-1]
            cover_info = json.loads(last)
            meta["cover"] = cover_info.get("cover")
            meta["cover_brief"] = cover_info.get("brief")
            meta["cover_workflow"] = cover_info.get("workflow")
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"🖼️ 封面已生成: {meta['cover']}")
            return cover_info
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"封面生成异常（已忽略，不影响小说正文）: {e}")
    return None


async def main():
    logger.info("=" * 50)
    logger.info("📰 每日短篇小说生成器启动")
    now = datetime.now(BJ)
    logger.info(f"时间: {now.strftime('%Y-%m-%d %H:%M')} (北京时间)")

    # Step 1: Search hot topics
    logger.info("🔍 搜索热点话题...")
    topics = await search_hot_topics()
    
    if not topics:
        logger.warning("搜索无结果，使用默认话题")
        topics = [{"title": "当代年轻人的生活压力与温情", "snippet": "社会民生"}]

    # Pick a topic
    topic_item = random.choice(topics)
    topic = f"{topic_item['title']} — {topic_item.get('snippet', '')}"
    logger.info(f"选中话题: {topic[:100]}")

    # Step 2: Select direction
    direction = select_direction()
    logger.info(f"选中方向: {direction['name']} {direction.get('sub', '')}")

    # Step 3: Generate novel
    logger.info("✍️ 开始创作...")
    novel = await generate_novel(topic, direction)

    if not novel or len(novel) < 500:
        logger.error("生成失败")
        sys.exit(1)

    # Step 4: Save
    path = save_novel(novel, topic, direction)
    logger.info(f"✅ 已保存: {path}")
    logger.info(f"📊 字数: {len(novel)}")

    # Step 5: Optional cover generation. Enable with GENERATE_COVER=1.
    cover_info = maybe_generate_cover(path, direction)
    
    # Print summary
    first_line = novel.strip().split("\n")[0]
    print(f"\n{'='*50}")
    print(f"📖 {first_line}")
    print(f"📝 {len(novel)} 字")
    print(f"📁 {path.name}")
    print(f"🎯 {direction['name']}")
    print(f"🔥 {topic[:80]}")
    if cover_info:
        print(f"🖼️ {cover_info.get('cover')}")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
