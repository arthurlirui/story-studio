"""集成测试：phase_complete 末尾三件交付物（清洗版 TXT、内容简介、封面提示词）。

用 FakeLLMClient 替代真实 LLM，根据 prompt 关键词返回不同的固定响应，
让 phase_complete 端到端跑完并产出文件，再断言各交付物：
- {project}_final.md（润色版，保留 markdown）
- {project}_final.txt（清洗版，无 markdown 标记、无段落编号、带扉页和章节标题）
- {project}_synopsis.txt（≤500 字简介）
- covers/cover_brief.json（author == "独孤元景 著"，title == 项目名）
- covers/cover_prompt.txt（纯英文视觉提示词）
- covers/*_workflow.json（book_cover_comfy --dry-run 产出的 workflow）

不依赖 pytest-asyncio：用 asyncio.run() 同步驱动 async 用例。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

# 让 tests/ 能 import 项目根模块

from config import StudioConfig
from orchestrator import StoryOrchestrator, DEFAULT_AUTHOR


def _run(coro):
    """新建 event loop 跑完协程，替代 pytest-asyncio。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fake LLM client ──────────────────────────────────────────


class FakeLLMClient:
    """根据 prompt 关键词路由到不同的固定响应，模拟整个 phase_complete 链路。"""

    def __init__(self):
        self.calls: list[str] = []

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        # 取最后一条 user 消息作为 prompt
        prompt = messages[-1]["content"] if messages else ""
        self.calls.append(prompt)
        return self._respond(prompt)

    def _respond(self, prompt: str) -> str:
        # 1. Final edit（编辑润色）
        if "最后一轮全文润色" in prompt:
            return (
                "# 第 1 章 觉醒\n\n"
                "陈风睁开眼，**剑光**劈开晨雾。\n\n"
                "## 一\n\n"
                "> 他知道，这一战避无可避。\n\n"
                "1. 第一段内容。\n"
                "2. 第二段内容。\n\n"
                "---\n\n"
                "![插图](x.png)\n\n"
                "*——第一章完——*\n"
            )
        # 2. 连续性检查
        if "最终连续性检查" in prompt:
            return "连续性检查通过。"
        # 3. 终审
        if "终审" in prompt:
            return "VERDICT: PASS\n\n作品达到交付标准。"
        # 4. 章节标题
        if "为以下每一章设计" in prompt and "章节标题" in prompt:
            return "第1章：觉醒\n"
        # 5. 内容简介
        # 注意：orchestrator 的 prompt 是 "**不超过 500 字**的内容简介"（含 markdown 星号）
        if "内容简介" in prompt and "500 字" in prompt:
            return (
                "陈风在乱世中觉醒，凭一柄破剑闯荡江湖，"
                "历经血战与背叛，最终直面宿命之敌。"
            )
        # 6. 封面 brief JSON
        if "封面设计师" in prompt and "JSON" in prompt:
            return json.dumps({
                "title": "测试书名（会被强制覆盖）",
                "subtitle": "奇幻武侠",
                "author": "会被覆盖",
                "genre": "Chinese wuxia fantasy",
                "mood": "epic, heroic, dramatic",
                "core_visual": "a lone swordsman facing a mountain of blades at dawn",
                "composition": "portrait book cover, centered composition, title-safe empty space at top and bottom",
                "palette": "ink black, blood red, cold silver, misty gray",
                "positive_prompt": (
                    "Book cover, premium novel cover artwork, Chinese wuxia fantasy, "
                    "a lone swordsman facing a mountain of blades at dawn, "
                    "portrait book cover, centered composition, title-safe empty space at top and bottom, "
                    "epic heroic dramatic mood, dramatic lighting, high detail, "
                    "painterly realistic illustration, professional publishing cover design, "
                    "ink black, blood red, cold silver, misty gray color palette"
                ),
            }, ensure_ascii=False)
        # 兜底
        return "（FakeLLM 兜底响应）"


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def orch(tmp_path):
    """构造一个用 FakeLLMClient 的 StoryOrchestrator，输出到 tmp_path。"""
    cfg = StudioConfig(
        backend="llm",
        llm_api_key="fake",
        knowledge_dir=str(tmp_path / "knowledge"),
        output_dir=str(tmp_path / "output"),
        scene_writers=1,
    )
    client = FakeLLMClient()
    orch = StoryOrchestrator(cfg, client=client)
    # 跳过生产环境的 3s 限流睡眠，让测试秒级跑完
    async def _no_pause():
        return None
    orch._rate_limit_pause = _no_pause
    orch.project_name = "测试小说"
    # 预置一章正文（含 markdown 标记，验证清洗效果）
    orch.knowledge.save_chapter(
        1,
        "# 第 1 章 觉醒\n\n"
        "陈风睁开眼，**剑光**劈开晨雾。\n\n"
        "## 一\n\n"
        "> 他知道，这一战避无可避。\n\n"
        "1. 第一段内容。\n"
        "2. 第二段内容。\n\n"
        "---\n\n"
        "![插图](x.png)\n\n"
        "*——第一章完——*\n",
        author="scene_writer",
    )
    return orch


# ── Tests ────────────────────────────────────────────────────


async def _phase_complete_produces_all_deliverables(orch):
    """端到端：phase_complete 应产出 .md、.txt、_synopsis.txt、cover_brief.json、
    cover_prompt.txt 五个文件。"""
    result = await orch.phase_complete()

    out_dir = Path(orch.cfg.output_dir)
    project = "测试小说"

    # 1. 润色版 MD（保留 markdown，由 editor 返回）
    md_path = out_dir / f"{project}_final.md"
    assert md_path.exists(), f"润色版 MD 未生成: {md_path}"
    md_content = md_path.read_text(encoding="utf-8")
    assert "第 1 章" in md_content

    # 2. 清洗版 TXT
    txt_path = out_dir / f"{project}_final.txt"
    assert txt_path.exists(), f"清洗版 TXT 未生成: {txt_path}"
    txt_content = txt_path.read_text(encoding="utf-8")

    # 3. 内容简介
    synopsis_path = out_dir / f"{project}_synopsis.txt"
    assert synopsis_path.exists(), f"内容简介未生成: {synopsis_path}"
    synopsis = synopsis_path.read_text(encoding="utf-8")
    assert len(synopsis) <= 500, f"简介超 500 字: {len(synopsis)}"
    # 验证内容真的来自 synopsis 分支（不是兜底串或 LLM 错误哨兵）
    assert "陈风" in synopsis, f"简介内容未来自 synopsis 分支: {synopsis!r}"

    # 4. 封面 brief JSON
    brief_path = out_dir / "covers" / "cover_brief.json"
    assert brief_path.exists(), f"封面 brief 未生成: {brief_path}"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))

    # 5. 封面纯英文提示词
    prompt_path = out_dir / "covers" / "cover_prompt.txt"
    assert prompt_path.exists(), f"封面提示词未生成: {prompt_path}"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    # 6. dry-run workflow JSON（由 book_cover_comfy.py --dry-run 写入）
    workflows = list((out_dir / "covers").glob("*_workflow.json"))
    assert workflows, "封面 workflow JSON 未生成（dry-run 失败？）"

    # 返回的 summary 应列出各交付物
    assert "终审" in result
    assert "清洗版 TXT" in result
    assert "内容简介" in result
    assert "封面 brief" in result


def test_phase_complete_produces_all_deliverables(orch):
    _run(_phase_complete_produces_all_deliverables(orch))


async def _clean_txt_has_no_markdown(orch):
    """清洗版 TXT 应去除所有 markdown 标记和段落编号。"""
    await orch.phase_complete()
    txt = Path(orch.cfg.output_dir, "测试小说_final.txt").read_text(encoding="utf-8")
    # 不应残留这些标记
    assert "**" not in txt, "TXT 仍含 ** 加粗标记"
    assert "##" not in txt, "TXT 仍含 ## 子标题"
    assert "![" not in txt, "TXT 仍含 ![]() 图片占位"
    # 段落编号（行首 1. / 2.）应被去除
    for line in txt.splitlines():
        stripped = line.lstrip()
        assert not stripped.startswith("1."), f"TXT 仍含段落编号: {line!r}"
        assert not stripped.startswith("2."), f"TXT 仍含段落编号: {line!r}"
    # 章末标记 *——完——* 应被去除
    assert "*——" not in txt, "TXT 仍含 *——完——* 章末标记"
    # 分隔线 --- 应被去除（独占一行的）
    for line in txt.splitlines():
        assert line.strip() != "---", "TXT 仍含 --- 分隔线"
    # 引用前缀 > 应被去除
    for line in txt.splitlines():
        assert not line.lstrip().startswith(">"), f"TXT 仍含 > 引用前缀: {line!r}"


def test_clean_txt_has_no_markdown(orch):
    _run(_clean_txt_has_no_markdown(orch))


async def _clean_txt_has_title_page_and_chapter_title(orch):
    """清洗版 TXT 应有书名+作者扉页，和每章的章节标题。"""
    await orch.phase_complete()
    txt = Path(orch.cfg.output_dir, "测试小说_final.txt").read_text(encoding="utf-8")
    # 扉页：书名 + 作者署名
    assert "《测试小说》" in txt, "TXT 缺少书名扉页"
    assert DEFAULT_AUTHOR in txt, f"TXT 缺少作者署名 {DEFAULT_AUTHOR}"
    # 章节标题（FakeLLM 返回 "第1章：觉醒"，应被解析为 "觉醒"）
    assert "觉醒" in txt, "TXT 缺少章节标题"


def test_clean_txt_has_title_page_and_chapter_title(orch):
    _run(_clean_txt_has_title_page_and_chapter_title(orch))


async def _cover_brief_author_and_title(orch):
    """cover_brief.json 的 author 必须是「独孤元景 著」，title 必须是项目名
    （即使 LLM 返回了别的值也应被强制覆盖）。"""
    await orch.phase_complete()
    brief = json.loads(
        Path(orch.cfg.output_dir, "covers", "cover_brief.json").read_text(encoding="utf-8")
    )
    assert brief["author"] == DEFAULT_AUTHOR, (
        f"author 应为 {DEFAULT_AUTHOR}，实际: {brief['author']!r}"
    )
    assert brief["title"] == "测试小说", (
        f"title 应为项目名 '测试小说'，实际: {brief['title']!r}"
    )


def test_cover_brief_author_and_title(orch):
    _run(_cover_brief_author_and_title(orch))


async def _cover_prompt_is_english(orch):
    """cover_prompt.txt 应是纯英文视觉提示词，不含中文。"""
    await orch.phase_complete()
    prompt = Path(orch.cfg.output_dir, "covers", "cover_prompt.txt").read_text(encoding="utf-8")
    assert prompt.startswith("Book cover"), f"提示词应以 'Book cover' 开头: {prompt[:50]!r}"
    # 不含中文字符
    chinese = [c for c in prompt if '\u4e00' <= c <= '\u9fff']
    assert not chinese, f"提示词含中文字符: {chinese[:10]}"


def test_cover_prompt_is_english(orch):
    _run(_cover_prompt_is_english(orch))


async def _phase_complete_with_review_criteria(orch):
    """review_criteria 参数应被附加到终审 prompt。"""
    client = orch.client
    criteria = "1. 荡气回肠\n2. 突出战争残酷"
    await orch.phase_complete(review_criteria=criteria)
    # 终审 prompt 应含评审标准
    review_prompts = [p for p in client.calls if "终审" in p]
    assert review_prompts, "未找到终审调用"
    assert criteria in review_prompts[-1], "review_criteria 未被附加到终审 prompt"


def test_phase_complete_with_review_criteria(orch):
    _run(_phase_complete_with_review_criteria(orch))


# ── 简介优雅截断测试 ────────────────────────────────────────


class LongSynopsisFakeLLM(FakeLLMClient):
    """返回超长简介，验证 _truncate_at_sentence 在句末标点处断开。"""

    def __init__(self, synopsis_text: str):
        super().__init__()
        self._synopsis = synopsis_text

    def _respond(self, prompt: str) -> str:
        # 简介请求的 prompt 含 "撰写一段**不超过 500 字**的内容简介"
        if "内容简介" in prompt and "500 字" in prompt:
            return self._synopsis
        return super()._respond(prompt)


@pytest.fixture
def orch_with_long_synopsis(tmp_path):
    """构造一个返回指定长简介的 orchestrator。"""
    def _make(synopsis_text: str) -> StoryOrchestrator:
        cfg = StudioConfig(
            backend="llm",
            llm_api_key="fake",
            knowledge_dir=str(tmp_path / "knowledge"),
            output_dir=str(tmp_path / "output"),
            scene_writers=1,
        )
        client = LongSynopsisFakeLLM(synopsis_text)
        o = StoryOrchestrator(cfg, client=client)
        async def _no_pause():
            return None
        o._rate_limit_pause = _no_pause
        o.project_name = "测试小说"
        o.knowledge.save_chapter(
            1,
            "# 第 1 章 觉醒\n\n陈风睁开眼。\n",
            author="scene_writer",
        )
        return o
    return _make


async def _synopsis_truncates_at_sentence(orch_with_long_synopsis):
    # 600 字带句号：应在最后一个句号处截断，且 ≤500
    sentence = "陈风在乱世中觉醒，凭一柄破剑闯荡江湖。"  # 20 字
    long_text = (sentence * 35).strip()  # ~700 字，多个句号
    orch = orch_with_long_synopsis(long_text)
    await orch.phase_complete()
    synopsis = Path(orch.cfg.output_dir, "测试小说_synopsis.txt").read_text(encoding="utf-8")
    assert len(synopsis) <= 500, f"简介超 500 字: {len(synopsis)}"
    # 应在句号处截断，结尾是句号
    assert synopsis.endswith("。"), f"应在句号处截断，实际结尾: {synopsis[-20:]!r}"


def test_synopsis_truncates_at_sentence(orch_with_long_synopsis):
    _run(_synopsis_truncates_at_sentence(orch_with_long_synopsis))


async def _synopsis_truncates_no_punctuation(orch_with_long_synopsis):
    # 600 字无标点长串：硬截断到 500 字
    long_text = "陈风" * 400  # 800 字无标点
    orch = orch_with_long_synopsis(long_text)
    await orch.phase_complete()
    synopsis = Path(orch.cfg.output_dir, "测试小说_synopsis.txt").read_text(encoding="utf-8")
    assert len(synopsis) <= 500, f"简介超 500 字: {len(synopsis)}"
    assert len(synopsis) > 0


def test_synopsis_truncates_no_punctuation(orch_with_long_synopsis):
    _run(_synopsis_truncates_no_punctuation(orch_with_long_synopsis))


async def _synopsis_short_unchanged(orch_with_long_synopsis):
    # 短简介（≤500）原样保留，不触发截断
    short_text = "这是一个短简介，不超过五百字，应原样保留。"
    orch = orch_with_long_synopsis(short_text)
    await orch.phase_complete()
    synopsis = Path(orch.cfg.output_dir, "测试小说_synopsis.txt").read_text(encoding="utf-8")
    assert synopsis == short_text, f"短简介被误改: {synopsis!r}"


def test_synopsis_short_unchanged(orch_with_long_synopsis):
    _run(_synopsis_short_unchanged(orch_with_long_synopsis))


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
