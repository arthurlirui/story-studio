"""
Short Story Engine — 番茄短故事生成模块
在 story-studio 基础上新增的轻量级短故事生成 Pipeline
"""
from __future__ import annotations
import asyncio, json, logging, time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Data Structures ──
@dataclass
class WorldviewCard:
    time: str = "当代"; place: str = "都市"; rules: str = ""
    society: str = ""; golden_finger: str = ""; mood_curve: str = ""
    def to_context(self) -> str:
        parts = [f"时代：{self.time}", f"地点：{self.place}"]
        for k in ["rules","society","golden_finger","mood_curve"]:
            v = getattr(self,k)
            if v: parts.append(f"{k}：{v}")
        return "\n".join(parts)

@dataclass
class SectionPlan:
    section: int; scene: str; word_target: int = 1500
    climax_level: str = "small"; knowledge_hint: str = ""

@dataclass
class StoryPlan:
    genre: str = ""; title: str = ""; synopsis: str = ""
    word_count: int = 15000; pov: str = "first_person"
    protagonist: dict = field(default_factory=dict)
    sections: list = field(default_factory=list)
    worldview_card: WorldviewCard = field(default_factory=WorldviewCard)
    knowledge_injections: list = field(default_factory=list)

    def build_context(self, up_to_section: int = 0) -> str:
        lines = [f"# 作品：{self.title}", f"# 简介：{self.synopsis}",
                 "", "## 世界观", self.worldview_card.to_context(),
                 "", "## 主角设定"]
        for k,v in self.protagonist.items():
            lines.append(f"- {k}：{v}")
        lines.append(""); lines.append("## 已完成章节")
        for s in self.sections[:up_to_section]:
            lines.append(f"- 第{s.section}节：{s.scene}")
        lines.append(""); return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"genre":self.genre,"title":self.title,"synopsis":self.synopsis,
                "word_count":self.word_count,"pov":self.pov,
                "protagonist":self.protagonist,
                "sections":[{"section":s.section,"scene":s.scene,
                "word_target":s.word_target,"climax_level":s.climax_level}
                for s in self.sections],
                "worldview_card":{"time":self.worldview_card.time,
                "place":self.worldview_card.place,"rules":self.worldview_card.rules}}

@dataclass
class SectionOutput:
    section: int; title: str = ""; text: str = ""; word_count: int = 0
    quality_issues: list = field(default_factory=list)

@dataclass
class StoryResult:
    title: str = ""; synopsis: str = ""; full_text: str = ""
    sections: list = field(default_factory=list)
    total_words: int = 0; generation_time_s: float = 0.0
# ── Skill Config Store ──
class SkillConfigStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir); self._cache: dict = {}
    def load(self, genre: str) -> dict:
        if genre in self._cache: return self._cache[genre]
        path = self.base_dir / f"{genre}.json"
        if path.exists():
            with open(path) as f: cfg = json.load(f)
        else: cfg = {"genre":genre,"category":"female","default_pov":"first_person","word_range":{"min":6000,"max":50000},"section_target":1500}
        self._cache[genre] = cfg; return cfg

# ── Quality Checker ──
class QualityChecker:
    """质量检查：开篇钩子、字数、结尾钩子"""
    @staticmethod
    def check(section: SectionOutput, sec_target: int) -> list[str]:
        issues = []
        if section.word_count < sec_target * 0.5:
            issues.append(f"字数不足: {section.word_count} < {sec_target*0.5:.0f}")
        if section.word_count > sec_target * 2.5:
            issues.append(f"字数超标: {section.word_count} > {sec_target*2.5:.0f}")
        text_clean = section.text.strip()
        if not text_clean: issues.append("空文本")
        if len(text_clean) < 100: issues.append("文本过短(<100字)")
        return issues

# ── Pipeline ──
class ShortStoryPipeline:
    _POLISH_TMPL: str | None = None  # 类级别缓存 polish_prompt.txt

    def __init__(self, llm_client, skill_store: SkillConfigStore,
                 knowledge_dir: Path, output_dir: Path):
        self.llm = llm_client; self.skills = skill_store
        self.knowledge_dir = Path(knowledge_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checker = QualityChecker()

    @staticmethod
    def _get_polish_template() -> str:
        """懒加载 polish_prompt.txt（类级别缓存，只读一次）"""
        if ShortStoryPipeline._POLISH_TMPL is not None:
            return ShortStoryPipeline._POLISH_TMPL
        candidates = [
            Path(__file__).parent.parent / "polish_prompt.txt",
            Path.home() / "code/story-studio/polish_prompt.txt",
        ]
        for p in candidates:
            if p.exists():
                tmpl = p.read_text("utf-8").strip()
                logger.info("已加载 polish_prompt.txt (%d字) from %s", len(tmpl), p)
                ShortStoryPipeline._POLISH_TMPL = tmpl
                return tmpl
        logger.warning("polish_prompt.txt 不存在，deai 将走裸润色")
        ShortStoryPipeline._POLISH_TMPL = "{section}"
        return ShortStoryPipeline._POLISH_TMPL

    async def generate(self, genre: str, prompt: str,
                       word_count: int = 15000,
                       worldview_overrides: dict | None = None,
                       enable_deai: bool = True) -> StoryResult:
        t0 = time.time()
        skill = self.skills.load(genre)
        pov = skill.get("default_pov","first_person")
        sec_target = skill.get("section_target",1500)
        logger.info("生成短故事: genre=%s words=%d deai=%s",genre,word_count,enable_deai)
        plan = await self._phase_plan(genre,prompt,word_count,pov,sec_target,skill,worldview_overrides or {})
        (self.output_dir/"story_plan.json").write_text(json.dumps(plan.to_dict(),ensure_ascii=False,indent=2),encoding="utf-8")
        logger.info("策划: title=%s sections=%d",plan.title,len(plan.sections))
        result = await self._phase_write(plan,skill)
        if enable_deai:
            result = await self._phase_deai(result, plan)
        result.generation_time_s = time.time()-t0
        (self.output_dir/"story_final.md").write_text(result.full_text,encoding="utf-8")
        logger.info("完成: %d words %.1fs",result.total_words,result.generation_time_s)
        return result

    async def _phase_plan(self, genre: str, prompt: str, word_count: int,
                          pov: str, sec_target: int, skill: dict,
                          worldview_overrides: dict) -> StoryPlan:
        num_sections = max(3, word_count // sec_target)
        genre_zh = {"rebirth_era":"重生/年代","modern_romance":"现代甜宠",
                    "ancient_palace":"古代宫斗","horror_rules":"悬疑规则怪谈",
                    "urban_system":"都市脑洞系统","apocalypse_scifi":"末世科幻",
                    "fierce_female":"大女主发疯","folk_occult":"民俗玄学",
                    "quick_transmig":"快穿","farming_business":"种田经营",
                    "cute_baby":"萌宝团宠","xianxia":"玄幻修仙",
                    "urban_martial":"都市高武","history_kingdom":"历史基建"}
        zh = genre_zh.get(genre,genre)
        system = f"""你是番茄短故事策划师，专精{zh}品类。
请根据用户需求，输出一个JSON格式的策划案，不要输出任何JSON之外的内容。
JSON格式：{{"title":"书名","synopsis":"100字简介",
"protagonist":{{"name":"","identity":"","goal":"","golden_finger":""}},
"sections":[{{"section":1,"scene":"节内容描述","climax_level":"small|medium|large"}}],
"worldview_card":{{"time":"时代","place":"地点","rules":"世界规则"}}}}"""
        user = f"""需求：{prompt}
字数：{word_count}字 共{num_sections}节 每节约{sec_target}字
叙事视角：{pov} {"第一人称" if pov=="first_person" else "第三人称"}
请输出JSON策划案："""
        raw = await self.llm.generate(user, system=system, temperature=0.8, max_tokens=4096)
        return self._parse_plan(raw, genre, word_count, pov)

    def _parse_plan(self, raw: str, genre: str, word_count: int, pov: str) -> StoryPlan:
        raw = raw.strip()
        if raw.startswith("```"): raw = raw[raw.index("\n")+1:raw.rindex("```")].strip()
        try: data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("JSON解析失败，使用原始文本兜底")
            return StoryPlan(genre=genre,title="未命名",synopsis=raw[:200],
                           word_count=word_count,pov=pov)
        sections = [SectionPlan(section=s["section"],scene=s["scene"],
                   climax_level=s.get("climax_level","small")) for s in data.get("sections",[])]
        wc = data.get("worldview_card",{})
        wcard = WorldviewCard(time=wc.get("time","当代"),place=wc.get("place","都市"),
                              rules=wc.get("rules",""))
        return StoryPlan(genre=genre,title=data.get("title","未命名"),
                       synopsis=data.get("synopsis",""),word_count=word_count,
                       pov=pov,protagonist=data.get("protagonist",{}),
                       sections=sections,worldview_card=wcard)
    async def _phase_write(self, plan: StoryPlan, skill: dict) -> StoryResult:
        """Phase 2: 逐节写作（含衔接上下文+重试）"""
        sections_out: list[SectionOutput] = []
        full_parts: list[str] = [f"# {plan.title}\n\n> {plan.synopsis}\n"]
        prev_text = ""
        for i, sp in enumerate(plan.sections):
            logger.info("写作 section %d/%d: %s", sp.section, len(plan.sections), sp.scene)
            context = plan.build_context(i)
            system = self._writer_system(plan, skill)
            user_prompt = self._section_writer_prompt(plan, sp, context, prev_text)
            text = await self._generate_with_retry(user_prompt, system, sp.word_target)
            so = self._process_section(sp.section, text, sp.word_target)
            quality_issues = self.checker.check(so, sp.word_target)
            if quality_issues:
                logger.warning("section %d 质量问题: %s", sp.section, quality_issues)
                so.quality_issues = quality_issues
            sections_out.append(so)
            full_parts.append(so.text)
            full_parts.append("")
            prev_text = so.text
        full_text = "\n".join(full_parts).strip()
        total_words = len(full_text.replace("\n","").replace(" ",""))
        return StoryResult(title=plan.title, synopsis=plan.synopsis,
                          full_text=full_text, sections=sections_out,
                          total_words=total_words)

    async def _generate_with_retry(self, prompt: str, system: str, word_target: int, max_retries: int = 2) -> str:
        """带重试的生成，处理 LLM 超时"""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await self.llm.generate(prompt, system=system, temperature=0.85, max_tokens=3072)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning("LLM 生成失败 (attempt %d/%d): %s，重试中...", attempt+1, max_retries+1, e)
                    await asyncio.sleep(2)
        raise last_error  # type: ignore[misc]

    def _writer_system(self, plan: StoryPlan, skill: dict) -> str:
        genre = skill.get("genre_name_zh", skill.get("genre", ""))
        checks = skill.get("quality_checks", [])
        hooks = skill.get("hook_templates", [])
        hook_hint = f"\n参考钩子模式：{' / '.join(hooks[:3])}" if hooks else ""
        check_lines = "\n".join(f"  - {c}" for c in checks[:6])
        return f"""你是番茄短故事写手，专精{genre}品类。
写作规则：
1. 每节开头3行必须出钩子{hook_hint}
2. 结尾留信息缺口让读者追更
3. 用对话和动作推进，不用旁白说明
4. 爽点密度：每2-3个小段落一个爽点
5. 人物情绪直给：愤怒就摔东西，开心就笑出声
6. 字数精确：目标字数误差不超过30%
7. 不要写"本章完""本节完"等收尾标记
质检要求：
{check_lines if check_lines else '  - 无特殊质检'}"""

    def _section_writer_prompt(self, plan: StoryPlan, sp, context: str, prev_text: str = "") -> str:
        """构建单节写作的 prompt，包含上一节结尾以确保衔接"""
        continuity = ""
        if prev_text:
            last_lines = prev_text.strip().split("\n")[-3:]
            continuity = f"\n## 上一节结尾（必须无缝衔接）：\n" + "\n".join(last_lines)
        return f"""{context}
## 本节任务
- 节号：第{sp.section}节
- 场景：{sp.scene}
- 目标字数：{sp.word_target}字
- 爽点等级：{sp.climax_level}
{continuity}
要求：
1. 开篇3行内出钩子（主角的行动/冲突/发现）
2. 衔接上一节结尾
3. 结尾留信息缺口
4. 不要写世界观说明，设定在行动中自然浮现
5. {"第一人称" if plan.pov=="first_person" else "第三人称"}
请直接输出本节正文（含节标题）："""

    def _process_section(self, sec_num: int, raw: str, word_target: int) -> SectionOutput:
        text = raw.strip()
        lines = text.split("\n")
        title = f"第{sec_num}节"
        if lines and (lines[0].startswith("#") or lines[0].startswith("第")):
            title = lines[0].lstrip("#").strip()
            text = "\n".join(lines[1:]).strip()
        wc = len(text.replace("\n","").replace(" ",""))
        return SectionOutput(section=sec_num, title=title, text=text, word_count=wc)

    # ── Phase 3: DeAI 去 AI 感润色 ──
    async def _phase_deai(self, result: StoryResult, plan: StoryPlan) -> StoryResult:
        """逐节去 AI 感润色 + 全文终润

        复用 run_all.py 的 deai 模块逻辑：
        - polish_prompt.txt 作为润色模板
        - 每节 3 次重试 + 429 指数退避
        - 输出替换到 result.sections 和 result.full_text
        """
        logger.info("=== deai 去AI感润色: %s ===", plan.title)
        polish_tmpl = ShortStoryPipeline._get_polish_template()

        SYSTEM = (
            "你是中国顶级网络小说编辑，擅长将好故事提升为精妙的网文作品。"
            "文字冷峻克制有张力，用细节和节奏感抓住读者。"
            "精通历史、悬疑、玄幻、言情、军事、医疗等专业题材。"
        )

        polished_sections = []
        full_parts = [f"# {plan.title}\n\n> {plan.synopsis}\n"]
        ok = fail = 0

        for so in result.sections:
            original = so.text
            orig_n = len(original)
            if orig_n < 100:
                logger.warning("  第%d节 太短(%d字), 跳过", so.section, orig_n)
                polished_sections.append(so)
                full_parts.append(original)
                full_parts.append("")
                continue

            # 构建 prompt：用润色模板包裹本节正文
            user = polish_tmpl.replace("{section}", original) if "{section}" in polish_tmpl else polish_tmpl.replace("{chapter}", original)
            logger.info("  第%d节 (%d字)...", so.section, orig_n)

            output = None
            last_err = None

            for attempt in range(3):
                try:
                    resp = await self.llm.chat(
                        messages=[
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": user},
                        ],
                        temperature=0.82,
                        max_tokens=6000,
                    )
                    text = resp.strip()
                    if text and len(text) > 50:
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
                pct = len(output) * 100 // orig_n if orig_n else 0
                logger.info("    ✅ 第%d节: %d→%d字 (%d%%)", so.section, orig_n, len(output), pct)
                polished = SectionOutput(
                    section=so.section, title=so.title,
                    text=output, word_count=len(output.replace("\n","").replace(" ",""))
                )
                polished_sections.append(polished)
                full_parts.append(output)
                full_parts.append("")
                ok += 1
            else:
                logger.error("    ❌ 第%d节: %s, 保留原文", so.section, last_err or "未知")
                polished_sections.append(so)
                full_parts.append(original)
                full_parts.append("")
                fail += 1

        full_text = "\n".join(full_parts).strip()
        total_words = len(full_text.replace("\n","").replace(" ",""))
        logger.info("  === deai 完毕: ✅%d  ❌%d | 总字数: %d→%d ===", ok, fail, result.total_words, total_words)

        return StoryResult(
            title=result.title, synopsis=result.synopsis,
            full_text=full_text, sections=polished_sections,
            total_words=total_words
        )
