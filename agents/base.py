"""
🤖 Agent 基类 — 所有创作 Agent 的抽象接口
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from typing import Any as _Any

logger = logging.getLogger(__name__)


class Agent(ABC):
    """Agent 基类.

    client 可以是 OllamaClient 或 VolcengineClient，
    只要实现了 chat(messages, model, temperature, max_tokens) -> str 接口即可。
    """

    def __init__(
        self,
        name: str,
        role: str,
        description: str,
        client: _Any,
        model: str = "ark-code-latest",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.name = name
        self.role = role
        self.description = description
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._conversation_history: list[dict[str, str]] = []

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Agent 的系统提示词."""
        ...

    async def think(self, prompt: str, context: str = "") -> str:
        """思考并回复。"""
        system = self.system_prompt
        if context:
            system = f"{system}\n\n## 当前已知信息\n\n{context}"

        messages = []
        # Add limited conversation history for continuity
        for msg in self._conversation_history[-6:]:
            messages.append(msg)

        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        self._conversation_history.append({"role": "user", "content": prompt})
        self._conversation_history.append({"role": "assistant", "content": response})

        if len(self._conversation_history) > 50:
            self._conversation_history = self._conversation_history[-30:]

        return response

    async def review(self, content: str, instructions: str = "") -> str:
        """审阅内容并给出反馈."""
        prompt = f"请审阅以下内容。{instructions}\n\n{content}"
        return await self.think(prompt)

    def reset_conversation(self):
        """重置对话历史."""
        self._conversation_history.clear()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "model": self.model,
        }
