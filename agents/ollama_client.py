"""
🧠 Ollama 推理客户端 — 本地模型推理引擎
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama 本地模型推理客户端."""

    def __init__(self, base_url: str = "http://localhost:11434", default_model: str = "qwen3.6-35b:latest"):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        system: str | None = None,
    ) -> str:
        """发送聊天请求到 Ollama."""
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": stream,
        }

        if system:
            # Prepend system message
            payload["messages"] = [{"role": "system", "content": system}] + payload["messages"]

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]

        except httpx.TimeoutException:
            logger.warning("Ollama timeout, retrying with shorter response...")
            payload["options"]["num_predict"] = min(max_tokens, 2048)
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]

        except Exception as e:
            logger.error("Ollama error: %s", e)
            return f"[Ollama error: {e}]"

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """简化接口：直接传入 prompt，自动组装成消息."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    async def check_health(self) -> bool:
        """检查 Ollama 服务是否正常."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict]:
        """列出本地可用模型."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return [
                        {"name": m["name"], "size": m["size"], "modified": m.get("modified_at", "")}
                        for m in data.get("models", [])
                    ]
                return []
        except Exception:
            return []


# 全局实例
client = OllamaClient()
