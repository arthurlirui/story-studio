"""
Trend Scout — 热榜情报搜集与方向生成模块
用豆包搜索主流小说平台，自动产出热门方向+大纲+去AI味润色
"""
from __future__ import annotations
import asyncio, json, subprocess, logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SEARCH_SCRIPT = Path.home() / ".openclaw/skills/byted-web-search/scripts/web_search.py"

PLATFORM_QUERIES = {
    "番茄-综合": "番茄小说 2026年 热门短故事 排行榜 趋势 爆款 题材",
    "番茄-官方": "番茄短故事 千字万金 激励计划 热门故事 签约 官方推荐",
    "起点-月票": "起点中文网 月票榜 热门小说 排行榜 趋势 2026",
    "七猫-女频": "七猫小说 女频 热榜 排行榜 2026 穿越 重生 言情",
    "七猫-男频": "七猫小说 男频 热榜 排行榜 2026 都市 神医 战神",
    "晋江-排行": "晋江文学城 金榜 编辑推荐 热门 短篇 2026",
    "红果-短剧": "红果短剧 热门榜 TOP10 AI漫剧 2026 重生 穿越 国风",
}

@dataclass
class TrendSignal:
    platform: str
    direction: str
    heat_level: int  # 1-5
    keywords: list[str]
    representative_work: str = ""
    notes: str = ""

@dataclass
class TrendReport:
    search_time: str = ""
    signals: list[TrendSignal] = field(default_factory=list)
    top_directions: list[dict] = field(default_factory=list)
    raw_summary: str = ""

class TrendScout:
    """热榜搜集器"""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    def search_platform(self, query_name: str, query: str, count: int = 8) -> str:
        """单次搜索，返回原始结果文本"""
        cmd = ["python3", str(SEARCH_SCRIPT), query, "--count", str(count)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=SEARCH_SCRIPT.parent)
            output = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
            if result.returncode != 0:
                output += f"\n[stderr]: {result.stderr[-500:]}"
            return output
        except subprocess.TimeoutExpired:
            return "[搜索超时]"
        except Exception as e:
            return f"[搜索出错: {e}]"

    async def search_all_platforms(self) -> dict[str, str]:
        """并行搜所有平台"""
        results = {}
        for name, query in PLATFORM_QUERIES.items():
            logger.info("搜索: %s", name)
            results[name] = self.search_platform(name, query)
        return results

    async def analyze_and_generate_directions(self, search_results: dict[str, str]) -> TrendReport:
        """用LLM分析搜索结果，提炼方向和生成大纲（如果LLM可用）"""
        if not self.llm:
            return self._basic_analysis(search_results)

        combined = "\n\n---\n\n".join(f"## {k}\n{v}" for k, v in search_results.items())
        system = """你是小说市场分析师+短故事策划。根据搜索数据提炼高潜力方向并设计大纲。
输出JSON格式，不要JSON之外的内容：
{"directions":[{"name":"方向名","heat":1-5,"rationale":"30字理由","genre":"品类","word_target":5000,
"title_options":["标题1","标题2","标题3"],
"synopsis":"一句话简介","protagonist":{"name":"","identity":"","golden_finger":"","personality":""},
"sections":[{"section":1,"title":"节标题","scene":"核心场景","climax":"冲突/爽点","words":1500}]}]}"""
        prompt = f"联网搜索结果如下。提炼5-6个短故事方向，每个配完整大纲：\n\n{combined[-12000:]}"
        raw = await self.llm.generate(prompt, system=system, temperature=0.7, max_tokens=8192)
        return self._parse_llm_analysis(raw, search_results)

    def _parse_llm_analysis(self, raw: str, results: dict) -> TrendReport:
        try:
            raw = raw.strip()
            if raw.startswith("```"): raw = raw[raw.index("\n")+1:raw.rindex("```")].strip()
            data = json.loads(raw)
            return TrendReport(
                search_time="", top_directions=data.get("directions", []),
                raw_summary=json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            return self._basic_analysis(results)

    def _basic_analysis(self, results: dict) -> TrendReport:
        return TrendReport(search_time="", raw_summary="\n\n".join(f"### {k}\n{v[:500]}" for k, v in results.items()))

    async def full_pipeline(self) -> dict:
        """完整流程：搜→分析→出方向+大纲"""
        logger.info("启动热榜搜集全流程")
        search_results = await self.search_all_platforms()
        report = await self.analyze_and_generate_directions(search_results)
        return {
            "search_results": search_results,
            "report": report,
            "direction_count": len(report.top_directions),
        }


# ── 大纲润色器 ──

DEAI_SYSTEM = """你是短故事大纲润色专家。你的任务是把结构化大纲改写成"写手交流笔记"风格。

规则：
1. 用口语化语言，像两个写手在聊怎么搞这篇
2. 标创作要点和爽点节奏
3. 绝对不用这些词：首先、其次、总而言之、值得注意的是、此外、基于、通过、充分、深入、从而、因此、需要指出的是
4. 用网感短句，多用"然后""这里""直接""就是""读者看到这..."
5. 保持专业创作建议的内核，只换表达方式
6. 不要改写章节正文，改的是大纲/创作思路部分"""

class OutlinePolisher:
    """大纲去AI味润色器"""

    def __init__(self, llm_client):
        self.llm = llm_client

    async def polish_outline(self, outline_text: str) -> str:
        if not self.llm:
            return outline_text
        prompt = f"把这个大纲改写成写手交流笔记风格，去AI味：\n\n{outline_text}"
        return await self.llm.generate(prompt, system=DEAI_SYSTEM, temperature=0.9, max_tokens=4096)

    async def polish_opening(self, opening_text: str, genre: str) -> str:
        """单独润色开篇300字，去模板感"""
        if not self.llm:
            return opening_text
        prompt = f"""润色这段番茄短故事开头，要求：
1. 删掉"我睁开眼""我重生在了"等套路开头
2. 用具体的动作/感官/对话开场
3. 保持{genre}品类调性
4. 300字左右
原文：{opening_text}"""
        return await self.llm.generate(prompt, system=DEAI_SYSTEM, temperature=0.9, max_tokens=2048)
