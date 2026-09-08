"""
DeaiEngine — 去AI化主引擎。
协调四层流程：规则扫描→纯规则重写→LLM重写→审计评分。
"""
from __future__ import annotations
import logging
import re
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rules import RULES, STRATEGY_DELETE, STRATEGY_REPLACE, STRATEGY_WEAKEN, STRATEGY_REWRITE

logger = logging.getLogger(__name__)

# 默认 prompts 目录（deai/prompts/）
_DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"

# 提示词 {segments} 占位符
_PROMPT_SEGMENTS_PLACEHOLDER = "{segments}"

# 内置 v1 提示词回退（文件缺失时用）
_BUILTIN_REWRITE_PROMPT_V1 = (
    "你是资深文学编辑。以下段落有明显AI写作痕迹，请用自然的人类口吻重写，"
    "保留原意和剧情走向，去掉浮夸修饰词、三段式排比、强行升华的结尾。\n\n"
    "## 输出格式（必须严格遵守）\n"
    "每段重写结果以 `[N]` 开头（N 为段落编号，与输入对应），段与段之间用空行分隔。\n"
    "不要输出任何思考过程、分析或标注，只输出重写后的正文。\n\n"
    "## 规则\n"
    "- 句子长短交替，别太整齐\n"
    "- 删掉'无比''极其'深深的'等空壳修饰词\n"
    "- 别用'不仅是…更是…'句式\n"
    "- 直接陈述，别绕弯子\n\n"
    "## 待重写段落\n" + _PROMPT_SEGMENTS_PLACEHOLDER
)

# ── 同义词替换表 ──
SYNONYM_TABLE: dict[str, list[str]] = {
    "然而": ["但", "可", "不过", "谁知", "哪知道"],
    "因此": ["所以", "于是", "这么一来", "结果"],
    "此外": ["还有", "另外", "同时", "再说"],
    "总之": ["说到底", "一句话", "说白了"],
    "显然": ["谁都看得出", "很明显", "不用想也知道"],
    "与此同时": ["同时", "这时候", "这会子"],
    "忽然": ["突然", "猛地", "一下子就"],
    "于是": ["这就", "便", "接着"],
    "终于": ["最后", "总算是", "算是"],
}

# ── 浮夸修饰弱化表 ──
WEAKEN_TABLE: dict[str, str] = {
    "无比": "很", "极其": "很", "深深": "", "不禁": "",
    "仿佛": "像", "宛如": "像", "霎时间": "忽然", "顷刻间": "突然",
    "映入眼帘": "出现", "无与伦比": "非常好", "不可磨灭": "难忘",
    "熠熠生辉": "闪亮", "令人惊叹": "很不错", "充满了生机": "有活力",
}

# ── 填充短语删除表 ──
FILLER_PATTERNS: list[str] = [
    r"值得注意的是.{1,30}，?",
    r"我们可以发现.{1,30}，?",
    r"事实上，?",
    r"基本上，?",
    r"在这个时间点，?",
    r"为了实现这一目标，?",
    r"整体而言，?",
    r"从某种程度上说，?",
]

@dataclass
class ScanResult:
    """单条规则命中结果。"""
    rule_id: int
    rule_name: str
    category: str
    severity: int
    match_count: int
    samples: list[str] = field(default_factory=list)

@dataclass  
class DeaiReport:
    """去AI化处理报告。"""
    scan_results: list[ScanResult] = field(default_factory=list)
    rules_rewritten: int = 0
    llm_rewritten: int = 0
    quality_score: int = 0
    summary: str = ""


class DeaiEngine:
    """去AI化引擎。
    
    使用方式:
        engine = DeaiEngine(llm_client=client)
        clean_text, report = await engine.process(text, seed=42)
    """
    
    def __init__(
        self,
        llm_client: Any = None,
        aggressiveness: float = 0.4,
        *,
        length_band: tuple[float, float] | None = None,
        prompt_version: str = "v1",
        prompts_dir: Path | str | None = None,
        audit_threshold: int = 35,
    ):
        self.client = llm_client
        self.aggr = max(0.0, min(1.0, aggressiveness))
        # 字数合规区间 (min_ratio, max_ratio)，None 表示不约束
        self.length_band = length_band
        self.audit_threshold = audit_threshold
        self._rng = random.Random()
        # LLM 重写提示词
        self._prompts_dir = Path(prompts_dir) if prompts_dir else _DEFAULT_PROMPTS_DIR
        self.prompt_version = prompt_version
        self._rewrite_prompt = self._load_rewrite_prompt(prompt_version)

    def _load_rewrite_prompt(self, version: str) -> str:
        """按版本加载 LLM 重写提示词，找不到回退内置 v1。"""
        p = self._prompts_dir / f"rewrite_{version}.txt"
        if p.exists():
            return p.read_text(encoding="utf-8")
        logger.warning("deai 重写提示词 %s 不存在，回退内置 v1", p)
        return _BUILTIN_REWRITE_PROMPT_V1

    def set_seed(self, seed: int) -> None:
        self._rng = random.Random(seed)

    # ── 层级1: 规则扫描 ──
    async def scan(self, text: str) -> list[ScanResult]:
        """扫描文本，返回所有命中的AI痕迹规则。"""
        results = []
        for rule in RULES:
            if not rule.patterns:
                continue
            total_matches = 0
            samples = []
            for pat in rule.patterns:
                try:
                    matches = re.findall(pat, text)
                    total_matches += len(matches)
                    samples.extend(matches[:3])
                except re.error:
                    continue
            if total_matches > 0:
                results.append(ScanResult(
                    rule_id=rule.id, rule_name=rule.name,
                    category=rule.category, severity=rule.severity,
                    match_count=total_matches, samples=samples,
                ))
        results.sort(key=lambda r: -r.severity)
        return results

    # ── 层级2: 纯规则重写 ──
    async def rewrite_rules(self, text: str) -> tuple[str, int]:
        """纯规则重写：替换/删除/弱化。返回 (新文本, 改写次数)。"""
        count = 0
        
        # 2a. 删除类规则 — 匹配整句后移除
        for rule in RULES:
            if rule.strategy != STRATEGY_DELETE or not rule.patterns:
                continue
            for pat in rule.patterns:
                new, n = re.subn(pat + r'.{0,50}?[。！？\n]', '', text)
                if n:
                    text = new
                    count += n

        # 2b. 弱化类规则 — 规则表 patterns 驱动（直接删除命中片段）
        # 规则表里 STRATEGY_WEAKEN 的 patterns 在重写阶段曾被忽略，
        # 这里接入规则驱动处理；下方 WEAKEN_TABLE 作为补充表覆盖规则未列出的词。
        for rule in RULES:
            if rule.strategy != STRATEGY_WEAKEN or not rule.patterns:
                continue
            for pat in rule.patterns:
                try:
                    text, n = re.subn(pat, '', text)
                    if n:
                        count += n
                except re.error:
                    continue

        # 2b'. WEAKEN_TABLE 补充表（规则表未覆盖的浮夸修饰词）
        for old, new in WEAKEN_TABLE.items():
            pattern = re.compile(re.escape(old))
            text, n = pattern.subn(new, text)
            count += n

        # 2c. 同义词变异（概率=aggr*0.5）
        for word, alternatives in SYNONYM_TABLE.items():
            if self._rng.random() < self.aggr * 0.5:
                replacement = self._rng.choice(alternatives)
                pattern = re.compile(r'(?<=\n)' + re.escape(word) + r'[，,]?\s*')
                text, n = pattern.subn(replacement, text)
                count += n

        # 2c'. REPLACE 类规则 — 规则表 patterns 驱动
        # 规则表里 STRATEGY_REPLACE（AI高频词汇/破折号/弯引号等）曾被重写阶段忽略，
        # 这里接入；命中后直接删除（高频词多为可去填充）。
        for rule in RULES:
            if rule.strategy != STRATEGY_REPLACE or not rule.patterns:
                continue
            for pat in rule.patterns:
                try:
                    text, n = re.subn(pat, '', text)
                    if n:
                        count += n
                except re.error:
                    continue

        # 2d. 填充短语删除（FILLER_PATTERNS 补充表，与规则 22 互补）
        for pat in FILLER_PATTERNS:
            text, n = re.subn(pat, '', text)
            count += n
        
        # 2e. 段落碎片化（大段落随机切分）
        if self.aggr > 0 and self._rng.random() < self.aggr * 0.25:
            text = self._fragment_paragraphs(text)
            count += 1
        
        # 2f. 超长句拆分（>100字句中位逗号截断）
        if self.aggr > 0:
            text = self._split_long_sentences(text)
        
        # 归一化空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
        
        return text.strip(), count

    def _fragment_paragraphs(self, text: str) -> str:
        """大段落（6行+）随机切为两段。"""
        paras = text.split('\n\n')
        new_paras = []
        for para in paras:
            lines = [l for l in para.split('\n') if l.strip()]
            if len(lines) >= 6 and self._rng.random() < 0.3:
                split_at = len(lines) // 2 + self._rng.randint(0, len(lines) // 6)
                split_at = min(split_at, len(lines) - 2)
                new_paras.append('\n'.join(lines[:split_at]))
                new_paras.append('\n'.join(lines[split_at:]))
            else:
                new_paras.append(para)
        return '\n\n'.join(new_paras)

    def _split_long_sentences(self, text: str) -> str:
        """100字以上的句子以概率在句中逗号处截断。"""
        sentences = re.split(r'(?<=[。！？])', text)
        new_parts = []
        for sent in sentences:
            if len(sent) > 100 and self._rng.random() < self.aggr * 0.5:
                commas = [m.start() for m in re.finditer(r'[，,；;]', sent)]
                if commas:
                    mid = commas[len(commas) // 2]
                    sent = sent[:mid+1] + '\n' + sent[mid+1:].lstrip('，,')
            new_parts.append(sent)
        return ''.join(new_parts)

    # ── 层级3: LLM 重写兜底 ──
    async def rewrite_llm(self, text: str, scan_results: list[ScanResult]) -> tuple[str, int]:
        """对规则无法自动处理的段落（STRATEGY_REWRITE）用LLM重写。
        
        返回 (新文本, 实际替换成功的段数)。

        对齐协议：送入 prompt 的每段加 [N] 锚号前缀，要求 LLM 输出保持 [N] 前缀，
        解析时按锚号回填，避免按位置对齐导致的错位。匹配失败时归一化兜底，
        仍失败则 warning 并跳过，不再静默失败、计数不再虚高。
        """
        if not self.client:
            return text, 0

        # 收集需要重写的段落上下文（scan 快照，可能在 rewrite_rules 后已变动文本，
        # 因此回填时用归一化匹配而非精确子串）
        rewrite_segments: list[str] = []
        for sr in scan_results:
            for sample in sr.samples[:3]:
                if sample and len(sample) > 10:
                    rewrite_segments.append(sample)

        if not rewrite_segments:
            return text, 0

        # 最多取 5 段，加 [N] 锚号前缀
        segments_to_send = rewrite_segments[:5]
        numbered = [f"[{i+1}] {s}" for i, s in enumerate(segments_to_send)]
        segments_block = "\n\n".join(numbered)

        prompt = self._rewrite_prompt.replace(_PROMPT_SEGMENTS_PLACEHOLDER, segments_block)
        # 兼容旧占位符写法
        if _PROMPT_SEGMENTS_PLACEHOLDER not in self._rewrite_prompt:
            prompt = self._rewrite_prompt + "\n\n## 待重写段落\n" + segments_block

        try:
            from agents.llm_client import LLM_ERROR_PREFIX

            response = await self.client.think(prompt)
            # 校验 LLMClient 的错误哨兵（"[LLM API error: ...]"）
            if not response or response.startswith(LLM_ERROR_PREFIX):
                logger.warning("deai LLM 重写返回错误哨兵，跳过")
                return text, 0

            # 解析 [N] 锚号 → 重写后正文
            rewritten_map = self._parse_numbered_response(response)
            if not rewritten_map:
                logger.warning("deai LLM 重写响应未解析出任何 [N] 段落，跳过")
                return text, 0

            actual_replaced = 0
            for idx, original_seg in enumerate(segments_to_send, start=1):
                new_seg = rewritten_map.get(idx)
                if not new_seg:
                    logger.warning("deai LLM 重写段落 [%d] 缺失响应，跳过", idx)
                    continue
                replaced = self._replace_segment(text, original_seg, new_seg)
                if replaced is not None:
                    text = replaced
                    actual_replaced += 1
                else:
                    logger.warning("deai LLM 重写段落 [%d] 未匹配原文，跳过", idx)
            return text, actual_replaced
        except Exception:
            logger.exception("deai LLM 重写异常，跳过")
            return text, 0

    @staticmethod
    def _normalize(s: str) -> str:
        """归一化：去首尾空白、压缩连续空白。用于段落匹配兜底。"""
        return re.sub(r"\s+", "", s.strip())

    @staticmethod
    def _parse_numbered_response(response: str) -> dict[int, str]:
        """从 LLM 响应解析 [N] 前缀段落，返回 {编号: 正文}。

        容错：[N] 后可能紧跟空格或换行；未带前缀的行归入上一段。
        """
        result: dict[int, str] = {}
        current_idx: int | None = None
        current_buf: list[str] = []
        for line in response.splitlines():
            m = re.match(r"^\s*\[(\d+)\]\s?(.*)$", line)
            if m:
                if current_idx is not None:
                    result[current_idx] = "\n".join(current_buf).strip()
                current_idx = int(m.group(1))
                current_buf = [m.group(2)] if m.group(2) else []
            else:
                if current_idx is not None and line.strip():
                    current_buf.append(line)
        if current_idx is not None:
            result[current_idx] = "\n".join(current_buf).strip()
        return result

    def _replace_segment(self, text: str, original: str, new: str) -> str | None:
        """在 text 中定位 original 段落并替换为 new。

        先精确子串匹配；失败则归一化后按段落扫匹配；仍失败返回 None。
        """
        if original in text:
            return text.replace(original, new, 1)
        # 归一化兜底：按段落块比对
        norm_orig = self._normalize(original)
        if not norm_orig:
            return None
        # 尝试按换行切段比对
        for chunk_sep in ("\n\n", "\n"):
            chunks = text.split(chunk_sep)
            for i, chunk in enumerate(chunks):
                if self._normalize(chunk) == norm_orig:
                    chunks[i] = new
                    return chunk_sep.join(chunks)
        return None

    # ── 层级4: 反AI审计 + 质量评分 ──
    async def audit(self, original: str, processed: str) -> tuple[int, str]:
        """对比处理前后，给出质量评分(0-50)和摘要。"""
        # 再次扫描处理后的文本
        after_scan = await self.scan(processed)
        before_scan = await self.scan(original)

        # 计算改善幅度
        before_total = sum(s.match_count * s.severity for s in before_scan)
        after_total = sum(s.match_count * s.severity for s in after_scan)
        improvement = before_total - after_total

        # 评分：消除幅度映射到0-50
        if before_total == 0:
            score = 45  # 原文没有AI痕迹
        else:
            reduction_ratio = improvement / before_total
            score = int(30 + reduction_ratio * 20)
            score = min(50, max(0, score))

        # 摘要
        if score >= 45:
            grade = "优秀，已去除AI痕迹"
        elif score >= 35:
            grade = "良好，仍有轻微痕迹"
        else:
            grade = "需进一步修订"

        summary = (
            f"去AI化审计: 改善{improvement}点, 评分{score}/50 — {grade}\n"
            f"处理前命中规则: {len(before_scan)}类\n"
            f"处理后命中规则: {len(after_scan)}类"
        )
        return score, summary

    # ── 主流程 ──
    async def process(self, text: str, seed: int | None = None) -> tuple[str, DeaiReport]:
        """完整去AI化流程：扫描→规则重写→LLM重写→审计。

        Args:
            text: 待处理的文本（应为clean后的纯文本）。
            seed: 随机种子。

        Returns:
            (processed_text, DeaiReport)
        """
        if not text or not text.strip():
            return text, DeaiReport(summary="空文本，跳过")

        if seed is not None:
            self.set_seed(seed)

        report = DeaiReport()

        # 层级1: 扫描
        original = text
        scan_results = await self.scan(text)
        report.scan_results = scan_results

        # 层级2: 纯规则重写
        text, rule_count = await self.rewrite_rules(text)
        report.rules_rewritten = rule_count

        # 层级3: LLM重写（仅当有REWRITE策略的规则被命中时触发）
        rewrite_candidates = [sr for sr in scan_results 
                              if any(r.strategy == STRATEGY_REWRITE and r.id == sr.rule_id 
                                     for r in RULES)]
        if rewrite_candidates and self.client:
            text, llm_count = await self.rewrite_llm(text, rewrite_candidates)
            report.llm_rewritten = llm_count

        # 层级4: 审计评分（original vs processed 对比）
        score, summary = await self.audit(original, text)
        report.quality_score = score
        report.summary = summary

        return text, report