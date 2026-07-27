#!/usr/bin/env python3
"""
AI 文本检测器 — 用于验证 deai 润色效果

支持多种检测后端:
1. chinese-ai-detector-bert (HuggingFace, 本地, 免费)
2. 将来可扩展: Fast-DetectGPT, Binoculars, API 服务

用法:
    from deai.detector import AIDetector
    det = AIDetector()
    score = det.check("这是测试文本")  # 0-1, 越高越像AI生成
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger("deai.detector")


class AIDetectionResult:
    """检测结果"""
    def __init__(self, score: float, label: str, details: dict = None):
        self.score = score
        self.label = label
        self.details = details or {}

    def __repr__(self):
        return f"AIDetectionResult(score={self.score:.3f}, label={self.label})"

    def is_ai(self, threshold: float = 0.5) -> bool:
        return self.score >= threshold


class AIDetector:
    """AI文本检测器 — 默认使用腾讯云 (优先), 失败回退 HuggingFace"""

    MODEL_ID = "AnxForever/chinese-ai-detector-bert"
    MAX_LENGTH = 512
    BACKENDS = ["tencent", "huggingface"]

    def __init__(self, model_id: str = None, device: str = None,
                 backend: str = None):
        self.model_id = model_id or self.MODEL_ID
        self._device = device or ("cuda" if self._cuda_available() else "cpu")
        self._model = None
        self._tokenizer = None
        self._stats = {"total_checks": 0, "ai_count": 0, "human_count": 0}
        self._backend = None
        self._backend_order = [backend] if backend else self.BACKENDS

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _load(self):
        """懒加载模型"""
        if self._model is not None:
            return
        logger.info("加载 AI 检测模型: %s (device=%s)...", self.model_id, self._device)
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_id)
        self._model.to(self._device)
        self._model.eval()
        logger.info("AI 检测模型加载完成")

    def _detect_backend(self):
        """按优先级选择可用后端"""
        if self._backend:
            return self._backend

        for b in self._backend_order:
            if b == "tencent":
                try:
                    from deai.tencent_detector import load_credentials
                    sid, _ = load_credentials()
                    if sid:
                        self._backend = "tencent"
                        logger.info("AI检测后端: 腾讯云")
                        return self._backend
                except Exception:
                    pass
            elif b == "huggingface":
                try:
                    self._load()
                    self._backend = "huggingface"
                    logger.info("AI检测后端: HuggingFace (本地)")
                    return self._backend
                except Exception as e:
                    logger.debug("HuggingFace 不可用: %s", e)

        raise RuntimeError("无可用的 AI 检测后端")

    def check(self, text: str) -> AIDetectionResult:
        """检测文本 (同步包装, 内部处理腾讯云异步)"""
        backend = self._detect_backend()

        if backend == "tencent":
            return self._check_tencent(text)
        else:
            return self._check_hf(text)

    async def check_async(self, text: str) -> AIDetectionResult:
        """异步检测 (腾讯云)"""
        backend = self._detect_backend()
        if backend == "tencent":
            return await self._check_tencent_async(text)
        else:
            return self._check_hf(text)

    async def _check_tencent_async(self, text: str) -> AIDetectionResult:
        if not text or len(text.strip()) < 100:
            return AIDetectionResult(0.0, "unknown", {"reason": "文本太短"})

        from deai.tencent_detector import check as tc_check
        result = await tc_check(text)

        self._stats["total_checks"] += 1
        label = result["label"].lower()
        if label == "block":
            self._stats["ai_count"] += 1
            label = "ai"
        elif label == "pass":
            self._stats["human_count"] += 1
            label = "human"
        else:
            label = "ai" if result["score"] > 0.5 else "human"

        return AIDetectionResult(
            score=result["score"],
            label=label,
            details=result,
        )

    def _check_tencent(self, text: str) -> AIDetectionResult:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # 在运行中的事件循环里, 返回未完成的 future
            # 调用方需要 await
            raise RuntimeError("use check_async in async context")
        except RuntimeError:
            pass
        return asyncio.run(self._check_tencent_async(text))

    def _check_hf(self, text: str) -> AIDetectionResult:
        """检测单段文本"""
        self._load()
        import torch

        if not text or len(text.strip()) < 100:
            return AIDetectionResult(0.0, "unknown", {"reason": "文本太短"})

        inputs = self._tokenizer(
            text, return_tensors="pt", truncation=True,
            max_length=self.MAX_LENGTH, padding=True,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            ai_score = probs[0][1].item()
            human_score = probs[0][0].item()

        label = "ai" if ai_score > human_score else "human"

        self._stats["total_checks"] += 1
        if label == "ai":
            self._stats["ai_count"] += 1
        else:
            self._stats["human_count"] += 1

        return AIDetectionResult(
            score=ai_score,
            label=label,
            details={
                "ai_prob": ai_score,
                "human_prob": human_score,
                "text_length": len(text),
            }
        )

    def check_before_after(self, original: str, polished: str) -> Dict:
        """对比润色前后"""
        backend = self._detect_backend()
        if backend == "tencent":
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                raise RuntimeError("use check_before_after_async in async context")
            except RuntimeError:
                pass
            return asyncio.run(self._check_before_after_tencent(original, polished))
        else:
            before = self.check(original)
            after = self.check(polished)
            delta = before.score - after.score
            return {
                "before": before,
                "after": after,
                "improvement": delta,
                "verdict": "effective" if delta > 0.05 else (
                    "slight" if delta > 0.01 else "ineffective"
                ),
            }

    async def check_before_after_async(self, original: str, polished: str) -> Dict:
        """异步对比润色前后 (腾讯云)"""
        backend = self._detect_backend()
        if backend == "tencent":
            return await self._check_before_after_tencent(original, polished)
        else:
            return self.check_before_after(original, polished)

    async def _check_before_after_tencent(self, original: str, polished: str) -> Dict:
        from deai.tencent_detector import check_before_after as tc_compare
        return await tc_compare(original, polished)

    def batch_check(self, texts: List[str]) -> List[AIDetectionResult]:
        """批量检测"""
        return [self.check(t) for t in texts]

    def check_file(self, path: Path, compare_with: Path = None) -> Dict:
        """检测文件 (可选对比润色前文件)"""
        text = path.read_text("utf-8")
        result = self.check(text)

        output = {"file": str(path), "result": result}

        if compare_with and Path(compare_with).exists():
            original = Path(compare_with).read_text("utf-8")
            output["comparison"] = self.check_before_after(original, text)

        return output

    @property
    def stats(self) -> Dict:
        return dict(self._stats)


def generate_report(
    detector: AIDetector,
    original_dir: Path,
    polished_dir: Path,
    name: str = "",
) -> str:
    """生成润色前后 AI 检测对比报告"""
    lines = []
    lines.append(f"# AI检测报告: {name or polished_dir.name}")
    lines.append("")
    lines.append("| 章节 | 原文AI得分 | 润色后AI得分 | 改善 | 判定 |")
    lines.append("|------|-----------|------------|------|------|")

    originals = sorted(original_dir.glob("chapter_*.md"))
    total_improvement = 0
    effective_count = 0

    for orig in originals:
        ch = orig.stem.replace("chapter_", "")
        polished = polished_dir / f"chapter_{ch}.md"
        if not polished.exists():
            continue

        comp = detector.check_before_after(
            orig.read_text("utf-8"),
            polished.read_text("utf-8"),
        )

        before = comp["before"].score
        after = comp["after"].score
        delta = comp["improvement"]
        verdict = comp["verdict"]

        total_improvement += delta
        if delta > 0.05:
            effective_count += 1

        lines.append(
            f"| ch{ch} | {before:.3f} | {after:.3f} | {delta:+.3f} | {verdict} |"
        )

    avg = total_improvement / max(len(originals), 1)
    lines.append("")
    lines.append(f"**平均改善: {avg:+.3f}** | **有效章数: {effective_count}/{len(originals)}**")
    lines.append("")

    return "\n".join(lines)
