"""
DeaiEngine — 去AI化主引擎。
协调四层流程：规则扫描→纯规则重写→LLM重写→审计评分。
"""
from __future__ import annotations
import re
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rules import RULES, STRATEGY_DELETE, STRATEGY_REPLACE, STRATEGY_WEAKEN, STRATEGY_REWRITE

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
    
    def __init__(self, llm_client: Any = None, aggressiveness: float = 0.4):
        self.client = llm_client
        self.aggr = max(0.0, min(1.0, aggressiveness))
        self._rng = random.Random()

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
        
        # 2b. 弱化类规则 — 替换为朴素表达
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
        
        # 2d. 填充短语删除
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
        
        返回 (新文本, LLM调用次数)。"""
        if not self.client:
            return text, 0

        # 收集需要重写的段落上下文
        rewrite_segments = []
        for sr in scan_results:
            for sample in sr.samples[:3]:
                if sample and len(sample) > 10:
                    rewrite_segments.append(sample)

        if not rewrite_segments:
            return text, 0

        prompt = (
            "你是资深文学编辑。以下段落有明显AI写作痕迹，请用自然的人类口吻重写，"
            "保留原意和剧情走向，去掉浮夸修饰词、三段式排比、强行升华的结尾。\n\n"
            "## 规则\n"
            "- 句子长短交替，别太整齐\n"
            "- 删掉'无比''极其''深深的'等空壳修饰词\n"
            "- 别用'不仅是…更是…'句式\n"
            "- 直接陈述，别绕弯子\n\n"
            "## 待重写段落\n" + "\n---\n".join(rewrite_segments[:5]))

        try:
            from agents.llm_client import LLM_ERROR_PREFIX

            response = await self.client.think(prompt)
            # 校验 LLMClient 的错误哨兵（"[LLM API error: ...]"）；
            # 之前查的是 "ERROR" 前缀，永远匹配不上真实哨兵，
            # 错误文本会被当作重写结果混进正文
            if response and not response.startswith(LLM_ERROR_PREFIX):
                # 用 LLM 响应中提取的段落替换对应的原文段
                rewritten_segs = [s.strip() for s in response.split("\n---\n") if s.strip()]
                for i, seg in enumerate(rewrite_segments[: len(rewritten_segs)]):
                    if seg in text:
                        text = text.replace(seg, rewritten_segs[i])
                return text, len(rewritten_segs)
        except Exception:
            pass

        return text, 0

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