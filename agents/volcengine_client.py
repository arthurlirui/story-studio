"""
🧠 Volcengine 推理客户端 — 火山引擎 API 推理引擎

使用 OpenAI-compatible API 调用火山引擎上的模型。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Rate-limit retry config
MAX_RETRIES = 8
BASE_DELAY = 5.0  # seconds
MAX_DELAY = 120.0   # seconds


class VolcengineClient:
    """火山引擎 API 推理客户端 (OpenAI-compatible)."""

    def __init__(
        self,
        base_url: str = "https://ark.cn-beijing.volces.com/api/coding/v3",
        api_key: str = "",
        default_model: str = "ark-code-latest",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
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
        """发送聊天请求到火山引擎 API (OpenAI-compatible)，带 429 重试."""
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                if resp.status_code == 429:
                    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                    logger.warning(
                        "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue

                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

            except httpx.TimeoutException:
                logger.warning("Timeout, retrying with shorter response...")
                payload["max_tokens"] = min(max_tokens, 2048)
                continue

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                    logger.warning(
                        "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue
                last_error = e
                break

            except Exception as e:
                last_error = e
                break

        logger.error("Volcengine API error after %d retries: %s", MAX_RETRIES, last_error)
        return f"[Volcengine API error: {last_error}]"

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """简化接口：直接传入 prompt，自动组装成消息."""
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system,
        )

    async def check_health(self) -> bool:
        """检查 API 是否正常."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict]:
        """列出可用模型."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [
                        {"id": m.get("id", ""), "name": m.get("id", "")}
                        for m in data.get("data", [])
                    ]
                return []
        except Exception:
            return []


# 全局实例（需要从 config 初始化）
client: VolcengineClient | None = None


def init_client(base_url: str, api_key: str, default_model: str = "ark-code-latest") -> VolcengineClient:
    """初始化全局客户端."""
    global client
    client = VolcengineClient(base_url=base_url, api_key=api_key, default_model=default_model)
    return client
