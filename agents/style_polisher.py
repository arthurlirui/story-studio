"""
🎨 Style Polisher — 文学风格润色智能体

通过本地 Qwen + LoRA 模型对小说文本进行风格化润色。
每位「作家风格」对应一个训练好的 LoRA adapter，可独立配置。

支持的风格:
  - moyan (莫言): 幻觉现实主义、感官饱和、泥土气息、怪诞身体描写
  - (未来可扩展: murakami, yu_hua, etc.)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from agents.base import Agent
from agents.local_inference_client import LocalInferenceClient

logger = logging.getLogger(__name__)


# ── 风格注册表 ──────────────────────────────────────────────────
# 每个风格对应一个 LoRA adapter 路径和系统提示词
# 新增风格只需在此注册即可

STYLE_REGISTRY: dict[str, dict] = {
    "moyan": {
        "name": "莫言",
        "description": "幻觉现实主义、感官饱和、泥土气息、怪诞身体描写、说书人口吻",
        "lora_path": "/data/openclaw/workspace/lora-style-transfer/output/adapters/moyan-style-lora-9b",
        "base_model": "/data/openclaw/workspace/model/Qwen3.5-9B",
        "system_prompt": (
            "你是一位精通莫言文学风格的作家。请严格模仿莫言的笔触润色文字"
            "——幻觉现实主义、感官饱和、泥土气息、怪诞身体描写、说书人口吻。"
            "保留原文的故事情节、人物对话和核心意象，只在语言风格上进行转化。"
            "让文字有泥土的腥味，有汗水的咸味，有庄稼拔节的声音。\n\n"
            "重要：直接输出润色后的文字，不要输出任何思考过程、分析、"
            "解释、标注或Thinking Process。只输出润色后的纯文本。"
        ),
        "temperature": 0.8,
        "max_tokens": 2048,
    },
    # ── 未来扩展 ──
    # "murakami": {
    #     "name": "村上春树",
    #     "description": "都市孤独感、爵士节奏、超现实隐喻、冷调抒情",
    #     "lora_path": "/data/openclaw/workspace/lora-style-transfer/output/adapters/murakami-style-lora-9b",
    #     "base_model": "/data/openclaw/workspace/model/Qwen3.5-9B",
    #     "system_prompt": "你是一位精通村上春树文学风格的作家...",
    #     "temperature": 0.75,
    #     "max_tokens": 8192,
    # },
}


class StylePolisher(Agent):
    """风格润色智能体 — 使用本地 Qwen + LoRA 进行文学风格润色.

    与其他 Agent 不同，StylePolisher 使用本地推理客户端
    (LocalInferenceClient)，直接加载 Qwen 基座模型 + LoRA adapter。

    Usage:
        client = LocalInferenceClient(style="moyan")
        polisher = StylePolisher(client=client, style="moyan")
        result = await polisher.polish(text)
    """

    def __init__(
        self,
        client: Any = None,
        style: str = "moyan",
        name: str | None = None,
        role: str = "Style Polisher",
        description: str | None = None,
        model: str = "local-qwen-lora",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        style_config = STYLE_REGISTRY.get(style)
        if not style_config:
            raise ValueError(
                f"未知风格 '{style}'，已注册风格: {list(STYLE_REGISTRY.keys())}"
            )

        self.style = style
        self.style_config = style_config

        super().__init__(
            name=name or f"{style_config['name']}风格润色师",
            role=role,
            description=description or f"使用 {style_config['name']} 风格润色文字（本地 Qwen + LoRA）",
            client=client,
            model=model,
            temperature=temperature if temperature is not None else style_config["temperature"],
            max_tokens=max_tokens or style_config["max_tokens"],
        )

    @property
    def system_prompt(self) -> str:
        return self.style_config["system_prompt"]

    async def polish(
        self,
        text: str,
        instruction: str = "",
        chunk_size: int = 1200,
    ) -> str:
        """润色文本.

        Args:
            text: 待润色的原文
            instruction: 额外润色指令（可选）
            chunk_size: 分块大小（字符数），避免超出模型上下文
        Returns:
            润色后的文本
        """
        # 如果文本不长，直接润色
        if len(text) <= chunk_size:
            return await self._polish_chunk(text, instruction)

        # 长文本分块润色
        chunks = self._split_text(text, chunk_size)
        polished_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"润色第 {i+1}/{len(chunks)} 块 ({len(chunk)} 字)...")
            polished = await self._polish_chunk(chunk, instruction)
            polished_chunks.append(polished)

        return "\n\n".join(polished_chunks)

    async def _polish_chunk(self, chunk: str, extra_instruction: str = "") -> str:
        """润色单个文本块 — 使用 raw completion 匹配训练格式."""
        # 训练数据格式: "用莫言的笔触，写一段..." / "模仿莫言写人物，描写..."
        # 使用 raw completion 避免 chat template 引入思考过程
        prompt = f"用莫言的笔触，重写以下文字：\n\n{chunk}\n\n重写后的文字："

        result = await self.client.generate(
            prompt=prompt,
            system=self.system_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        result = result.strip()
        return self._strip_thinking(result)

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """移除模型输出的思考过程标记."""
        import re
        # 移除 Thinking Process 块
        text = re.sub(r'Thinking Process:.*?(?=\n\n[^\d]|\Z)', '', text, flags=re.DOTALL | re.IGNORECASE)
        # 移除编号的思考步骤
        text = re.sub(r'^\d+\.\s+\*\*[^*]+\*\*.*?(?=\n\n[^\d]|\Z)', '', text, flags=re.MULTILINE | re.DOTALL)
        # 移除 Self-Correction 块
        text = re.sub(r'\*\(Self-Correction[^)]*\):.*?(?=\n\n|\Z)', '', text, flags=re.DOTALL)
        # 移除 "Let's write it." 行
        text = re.sub(r"Let's write it\..*", '', text, flags=re.DOTALL)
        # 移除 cw/response 标记
        text = re.sub(r'^cw\n', '', text)
        text = re.sub(r'^response\n', '', text)
        # 清理多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _split_text(self, text: str, chunk_size: int) -> list[str]:
        """按段落边界分块，避免在段落中间截断."""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 <= chunk_size:
                current = f"{current}\n\n{para}" if current else para
            else:
                if current:
                    chunks.append(current)
                # 如果单个段落就超过 chunk_size，硬切
                if len(para) > chunk_size:
                    for i in range(0, len(para), chunk_size):
                        chunks.append(para[i:i + chunk_size])
                    current = ""
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks

    async def polish_file(
        self,
        input_path: str,
        output_path: str | None = None,
        instruction: str = "",
    ) -> str:
        """润色整个文件.

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径（默认在输入文件同目录加 _polished 后缀）
            instruction: 额外润色指令
        Returns:
            输出文件路径
        """
        input_path = str(input_path)
        text = Path(input_path).read_text(encoding="utf-8")

        logger.info(f"开始润色: {input_path} ({len(text)} 字)")
        polished = await self.polish(text, instruction)

        if output_path is None:
            p = Path(input_path)
            output_path = str(p.parent / f"{p.stem}_moyan{p.suffix}")

        Path(output_path).write_text(polished, encoding="utf-8")
        logger.info(f"润色完成: {output_path}")

        return output_path

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["style"] = self.style
        d["style_name"] = self.style_config["name"]
        d["lora_path"] = self.style_config["lora_path"]
        d["base_model"] = self.style_config["base_model"]
        return d


# ── 工厂函数 ────────────────────────────────────────────────────

def create_style_polisher(
    style: str = "moyan",
    client: Any = None,
) -> StylePolisher:
    """创建风格润色智能体.

    Args:
        style: 风格名称（见 STYLE_REGISTRY）
        client: 推理客户端（如未提供，将自动创建 LocalInferenceClient）
    Returns:
        StylePolisher 实例
    """
    if client is None:
        client = LocalInferenceClient(style=style)

    return StylePolisher(client=client, style=style)


# ── 列出可用风格 ────────────────────────────────────────────────

def list_styles() -> list[dict]:
    """列出所有已注册的风格."""
    return [
        {
            "key": k,
            "name": v["name"],
            "description": v["description"],
            "lora_path": v["lora_path"],
        }
        for k, v in STYLE_REGISTRY.items()
    ]
