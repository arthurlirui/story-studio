"""
LLM Client - OpenAI-compatible API (PCL LLM API)

Supports:
- reasoning field extraction (DeepSeek-R1 style chain-of-thought)
- streaming mode
- 429 rate-limit retry with exponential backoff
- timeout degradation
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 8
BASE_DELAY = 5.0
MAX_DELAY = 120.0
DEFAULT_TIMEOUT = 300.0

# 错误哨兵：所有 API 错误统一以此前缀返回，便于调用方用 startswith 检测
_ERROR_SENTINEL = "[LLM API error: {}]"


class LLMClient:
    """OpenAI-compatible API client with reasoning + streaming support."""

    def __init__(
        self,
        base_url: str = "https://llmapi.pcl.ac.cn/v1",
        api_key: str = "",
        default_model: str = "DeepSeek-V4-Pro",
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
    ) -> str | AsyncIterator[str]:
        """Send chat request. Returns full string (stream=False) or async generator (stream=True)."""
        payload_messages: list[dict[str, str]] = []
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

        if stream:
            return self._stream_chat(payload, headers)

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                if resp.status_code == 429:
                    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                    logger.warning("Rate limited (429), retry %.1fs (attempt %d/%d)", delay, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(delay)
                    continue

                resp.raise_for_status()
                data = resp.json()
                return self._extract_content(data)

            except httpx.TimeoutException:
                # 超时：将 max_tokens 减半后重试（下限 512，避免无限缩小）
                new_max = max(payload["max_tokens"] // 2, 512)
                logger.warning("Timeout (attempt %d/%d), reducing max_tokens %d→%d",
                               attempt + 1, MAX_RETRIES, payload["max_tokens"], new_max)
                payload["max_tokens"] = new_max
                continue

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                    logger.warning("Rate limited (429), retry %.1fs (attempt %d/%d)", delay, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(delay)
                    continue
                last_error = e
                break

            except Exception as e:
                last_error = e
                logger.error("Unexpected error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, e)
                break

        logger.error("API error after %d retries: %s", MAX_RETRIES, last_error)
        return _ERROR_SENTINEL.format(last_error)

    async def _stream_chat(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> AsyncIterator[str]:
        """Streaming chat iterator. Yields reasoning tokens first, then content tokens."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    ) as resp:
                        if resp.status_code == 429:
                            delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                            logger.warning("Rate limited (429) in stream, retry %.1fs (attempt %d/%d)", delay, attempt + 1, MAX_RETRIES)
                            await asyncio.sleep(delay)
                            continue

                        resp.raise_for_status()

                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue

                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue
                                delta = choices[0].get("delta", {})

                                reasoning = delta.get("reasoning")
                                if reasoning:
                                    yield reasoning

                                content = delta.get("content")
                                if content:
                                    yield content

                            except json.JSONDecodeError:
                                continue

                        return

            except httpx.TimeoutException:
                logger.warning("Stream timeout (attempt %d/%d)", attempt + 1, MAX_RETRIES)
                continue
            except Exception as e:
                last_error = e
                logger.error("Stream error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, e)
                break

        yield _ERROR_SENTINEL.format(last_error)

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        """Extract content from API response, supporting reasoning field.

        - If content exists, return content
        - If content is empty but reasoning exists, return reasoning
        - If both exist, return content (reasoning is chain-of-thought, not for user)
        """
        msg = data.get("choices", [{}])[0].get("message", {})
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning") or ""
        if content:
            return content
        if reasoning:
            return reasoning
        return ""

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Simplified interface: pass prompt, get response."""
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(  # type: ignore[return-value]
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system,
        )

    async def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Streaming simplified interface."""
        messages = [{"role": "user", "content": prompt}]
        result = await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system,
            stream=True,
        )
        async for token in result:  # type: ignore[union-attr]
            yield token

    async def check_health(self) -> bool:
        """Check if API is healthy."""
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
        """List available models."""
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


client: LLMClient | None = None


def init_client(base_url: str, api_key: str, default_model: str = "DeepSeek-V4-Pro") -> LLMClient:
    """Initialize global client."""
    global client
    client = LLMClient(base_url=base_url, api_key=api_key, default_model=default_model)
    return client
