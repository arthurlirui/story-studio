"""
🔄 Multi-Model Polisher — 多模型润色模块

支持用不同种类的 LLM 同时润色文字风格，输出各模型结果及 de-AI 评分对比，
使文字风格 AI 感下降。

用法:
    client = LLMClient(base_url=..., api_key=...)
    polisher = MultiModelPolisher(
        client=client,
        models=["DeepSeek-V4-Pro", "qwen-plus"],
        deai_engine=DeaiEngine(),
    )
    report = await polisher.polish(text)
    print(report.summary)
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.llm_client import LLM_ERROR_PREFIX
from deai.engine import DeaiEngine

logger = logging.getLogger(__name__)


# ── 数据类 ──────────────────────────────────────────────────────

@dataclass
class PolishResult:
    """单个模型的润色结果。"""
    model_name: str
    polished_text: str = ""
    deai_score: int = 0          # 去AI评分 (0-50)
    word_count: int = 0          # 润色后字数
    latency_ms: float = 0.0      # 耗时（毫秒）
    error: str | None = None     # 错误信息（成功时为 None）
    success: bool = True

    @property
    def grade(self) -> str:
        """根据 deai_score 返回评级标签。"""
        if self.deai_score >= 45:
            return "🏆 优秀"
        elif self.deai_score >= 35:
            return "✅ 良好"
        elif self.deai_score >= 25:
            return "⚠️ 一般"
        else:
            return "❌ 需改进"


@dataclass
class MultiModelPolishReport:
    """多模型润色对比报告。"""
    results: list[PolishResult] = field(default_factory=list)
    best_model: str = ""
    best_score: int = 0
    total_time_ms: float = 0.0
    summary: str = ""

    @property
    def ranked_results(self) -> list[PolishResult]:
        """按 deai_score 降序排列的结果列表。"""
        return sorted(self.results, key=lambda r: (-r.deai_score, r.model_name))

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.success)


# ── 主类 ────────────────────────────────────────────────────────

class MultiModelPolisher:
    """多模型润色器 — 用不同 LLM 同时润色文字，对比去 AI 效果。

    Usage:
        polisher = MultiModelPolisher(
            client=llm_client,
            models=["DeepSeek-V4-Pro", "qwen-plus"],
            deai_engine=DeaiEngine(),
            polish_prompt_path="polish_prompt_v4.txt",
            max_concurrent=3,
        )
        report = await polisher.polish("你的原文...")
    """

    def __init__(
        self,
        client: Any,
        models: list[str] | None = None,
        deai_engine: DeaiEngine | None = None,
        polish_prompt_path: str = "polish_prompt_v4.txt",
        max_concurrent: int = 3,
        default_temperature: float = 0.8,
        default_max_tokens: int = 12000,
    ):
        self.client = client

        if not models:
            raise ValueError("models 不能为空，请至少指定一个模型名")

        self.models = models
        self.deai_engine = deai_engine or DeaiEngine()
        self.max_concurrent = max(1, max_concurrent)
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

        # 加载润色提示词模板
        prompt_path = Path(polish_prompt_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"润色提示词文件不存在: {polish_prompt_path}")
        self._polish_template = prompt_path.read_text(encoding="utf-8")

    # ── 主入口 ──

    async def polish(
        self,
        text: str,
        instruction: str = "",
        model_temperatures: dict[str, float] | None = None,
        model_max_tokens: dict[str, int] | None = None,
    ) -> MultiModelPolishReport:
        """并发调用多个模型润色文本。

        Args:
            text: 待润色的原文
            instruction: 额外润色指令（追加到提示词末尾）
            model_temperatures: 各模型的 temperature 覆盖，如 {"model-a": 0.9}
            model_max_tokens: 各模型的 max_tokens 覆盖

        Returns:
            MultiModelPolishReport 包含所有模型的结果和对比信息
        """
        if not text or not text.strip():
            return MultiModelPolishReport(summary="⚠️ 空文本，跳过润色")

        temps = model_temperatures or {}
        tokens = model_max_tokens or {}

        start_time = time.monotonic()

        # 使用 Semaphore 控制并发
        sem = asyncio.Semaphore(self.max_concurrent)

        async def _polish_one(model: str) -> PolishResult:
            async with sem:
                return await self._polish_with_model(
                    text=text,
                    model=model,
                    instruction=instruction,
                    temperature=temps.get(model, self.default_temperature),
                    max_tokens=tokens.get(model, self.default_max_tokens),
                )

        # 并发执行
        results = await asyncio.gather(*[_polish_one(m) for m in self.models])

        total_time = (time.monotonic() - start_time) * 1000

        # 构建报告
        ranked = sorted(results, key=lambda r: (-r.deai_score if r.success else -1, r.model_name))

        report = MultiModelPolishReport(
            results=results,
            best_model=ranked[0].model_name if ranked and ranked[0].success else "N/A",
            best_score=ranked[0].deai_score if ranked and ranked[0].success else 0,
            total_time_ms=total_time,
        )

        # 生成摘要
        lines = [
            f"📊 多模型润色报告",
            f"   总耗时: {total_time:.0f}ms",
            f"   成功: {report.success_count} / 失败: {report.fail_count}",
            f"   最优模型: {report.best_model} (de-AI {report.best_score}/50)",
            "",
        ]
        for r in ranked:
            status = f"{r.grade} (de-AI {r.deai_score}/50)" if r.success else f"❌ 失败: {r.error}"
            lines.append(f"  {r.model_name}: {status} | {r.word_count}字 | {r.latency_ms:.0f}ms")

        report.summary = "\n".join(lines)
        return report

    # ── 单模型润色 ──

    async def _polish_with_model(
        self,
        text: str,
        model: str,
        instruction: str = "",
        temperature: float = 0.8,
        max_tokens: int = 12000,
    ) -> PolishResult:
        """使用单个模型润色文本并评分。

        Args:
            text: 原文
            model: 模型名
            instruction: 额外指令
            temperature: 采样温度
            max_tokens: 最大输出 token

        Returns:
            PolishResult
        """
        t0 = time.monotonic()

        # 构建提示词
        system_prompt = self._polish_template
        if instruction:
            system_prompt = f"{system_prompt}\n\n## 额外指令\n{instruction}"

        try:
            # 调用 LLM 润色
            polished = await self.client.chat(
                messages=[{"role": "user", "content": text}],
                model=model,
                system=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            latency = (time.monotonic() - t0) * 1000

            # 检查错误哨兵
            if polished and polished.startswith(LLM_ERROR_PREFIX):
                return PolishResult(
                    model_name=model,
                    error=polished,
                    success=False,
                    latency_ms=latency,
                )

            # 去AI评分
            original_for_audit = text
            deai_score, _ = await self.deai_engine.audit(
                original=original_for_audit,
                processed=polished,
            )

            word_count = len(polished)

            return PolishResult(
                model_name=model,
                polished_text=polished,
                deai_score=deai_score,
                word_count=word_count,
                latency_ms=latency,
                success=True,
            )

        except Exception as e:
            latency = (time.monotonic() - t0) * 1000
            logger.warning(f"模型 {model} 润色失败: {e}")
            return PolishResult(
                model_name=model,
                error=str(e),
                success=False,
                latency_ms=latency,
            )

    # ── 批量文件润色 ──

    async def polish_file(
        self,
        input_path: str,
        output_dir: str | None = None,
        instruction: str = "",
    ) -> MultiModelPolishReport:
        """润色整个文件，各模型结果分别保存。

        Args:
            input_path: 输入文件路径
            output_dir: 输出目录（默认 input_path 同目录下 multi-polish/）
            instruction: 额外润色指令

        Returns:
            MultiModelPolishReport
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        text = input_path.read_text(encoding="utf-8")
        logger.info(f"开始多模型润色: {input_path} ({len(text)} 字)")

        report = await self.polish(text, instruction)

        # 保存各模型结果
        out_dir = Path(output_dir) if output_dir else input_path.parent / "multi-polish"
        out_dir.mkdir(parents=True, exist_ok=True)

        stem = input_path.stem
        for r in report.results:
            if r.success:
                safe_model = r.model_name.replace("/", "_").replace("\\", "_")
                out_file = out_dir / f"{stem}_{safe_model}.md"
                out_file.write_text(r.polished_text, encoding="utf-8")
                logger.info(f"  {r.model_name} -> {out_file}")

        # 保存对比报告
        report_path = out_dir / f"{stem}_report.md"
        report_path.write_text(report.summary, encoding="utf-8")
        logger.info(f"  报告 -> {report_path}")

        return report


# ── 工厂函数 ────────────────────────────────────────────────────

def create_multi_polisher(
    client: Any,
    models: list[str],
    deai_engine: DeaiEngine | None = None,
    polish_prompt_path: str = "polish_prompt_v4.txt",
    max_concurrent: int = 3,
    default_temperature: float = 0.8,
    default_max_tokens: int = 12000,
) -> MultiModelPolisher:
    """创建多模型润色器。

    Args:
        client: LLMClient 实例
        models: 模型名列表
        deai_engine: DeaiEngine 实例（可选，自动创建）
        polish_prompt_path: 润色提示词文件路径
        max_concurrent: 最大并发数
        default_temperature: 默认 temperature
        default_max_tokens: 默认 max_tokens

    Returns:
        MultiModelPolisher 实例
    """
    return MultiModelPolisher(
        client=client,
        models=models,
        deai_engine=deai_engine,
        polish_prompt_path=polish_prompt_path,
        max_concurrent=max_concurrent,
        default_temperature=default_temperature,
        default_max_tokens=default_max_tokens,
    )
