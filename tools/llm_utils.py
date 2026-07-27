"""
共享 LLM API 调用工具。
集中管理各脚本中重复的 async LLM call 逻辑，避免散落多处定义。
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

import httpx


async def call_llm(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    *,
    api_base: str,
    api_key: str,
    model: str = "DeepSeek-V4-Pro",
    max_tokens: int = 8192,
    temperature: float = 0.9,
    max_retries: int = 3,
    timeout: float = 600.0,
) -> str:
    """通用 OpenAI 兼容 chat/completions 调用，带超时重试+429退避。

    Args:
        client: 复用 httpx.AsyncClient 实例。
        messages: 标准 OpenAI messages 列表。
        api_base: LLM API 基础 URL（如 https://llmapi.pcl.ac.cn/v1）。
        api_key: API 鉴权 Key。
        model: 模型名。
        max_tokens: 单次调用最大 token。
        temperature: 温度参数。
        max_retries: 最大重试次数（含首次调用）。
        timeout: HTTP 超时秒数。

    Returns:
        LLM 响应的文本内容；失败时返回空字符串。
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    endpoint = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for attempt in range(max_retries):
        try:
            resp = await client.post(endpoint, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                wait = 5 * (2 ** attempt)
                print(f"  Rate limited, retry in {wait}s (attempt {attempt+1})", file=sys.stderr)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  LLM attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    return ""
