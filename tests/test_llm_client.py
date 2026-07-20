"""单元测试：agents/llm_client.py 的 LLMClient。

覆盖 Stage 1.3 改动：
- 超时重试：第 1 次超时用原 max_tokens 重试，连续 2 次才减半（不永久崩塌）
- last_usage 提取：从 API response.usage 提取 token 用量
- 429 退避：exponential backoff
- 错误哨兵：终态错误返回 _ERROR_SENTINEL

全部用 monkeypatch mock httpx.AsyncClient，不触达真实网络。
"""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path


import httpx
import pytest

from agents.llm_client import LLMClient, _ERROR_SENTINEL, MAX_RETRIES, BASE_DELAY


# ── 测试辅助：mock httpx.AsyncClient ─────────────────────────

class MockResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = str(self._json)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "mock error", request=None, response=self,  # type: ignore[arg-type]
            )


class MockAsyncClient:
    """mock httpx.AsyncClient。responses 是一个 list，按调用顺序消费。"""

    def __init__(self, responses: list, raise_exc: Exception | None = None):
        # responses: 每个元素是 MockResponse 或 Exception（调用 post 时抛）
        self.responses = list(responses)
        self.raise_exc = raise_exc
        self.calls = []  # 记录每次 post 的 payload
        self.is_closed = False  # 兼容连接池复用检查

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.is_closed = True
        return False

    async def post(self, url, json=None, headers=None):
        # 深拷贝 payload，避免后续重试修改 max_tokens 时反向污染历史记录
        self.calls.append({"url": url, "json": copy.deepcopy(json), "headers": headers})
        if not self.responses:
            raise RuntimeError("MockAsyncClient: responses 已耗尽")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok_response(content: str = "hello", usage: dict | None = None) -> MockResponse:
    data = {
        "choices": [{"message": {"content": content, "reasoning": ""}}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return MockResponse(200, data)


def _make_client_with_mock(monkeypatch, responses, raise_exc=None):
    client = LLMClient(base_url="http://mock/v1", api_key="test-key", default_model="test-model")
    mock = MockAsyncClient(responses, raise_exc=raise_exc)

    def factory(*args, **kwargs):
        return mock

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return client, mock


# ── 超时重试：不永久减半 ────────────────────────────────────

class TestTimeoutRetry:
    def test_first_timeout_retries_same_max_tokens(self, monkeypatch):
        """第 1 次超时：用原 max_tokens 重试，不减半。"""
        responses = [
            httpx.TimeoutException("timeout 1"),
            _ok_response("recovered"),
        ]
        client, mock = _make_client_with_mock(monkeypatch, responses)

        result = asyncio.run(client.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=4096,
        ))

        assert result == "recovered"
        # 两次调用都应用 4096（第 2 次未减半）
        assert mock.calls[0]["json"]["max_tokens"] == 4096
        assert mock.calls[1]["json"]["max_tokens"] == 4096

    def test_two_consecutive_timeouts_halve_max_tokens(self, monkeypatch):
        """连续 2 次超时：第 3 次重试时减半。"""
        responses = [
            httpx.TimeoutException("timeout 1"),
            httpx.TimeoutException("timeout 2"),
            _ok_response("recovered after halve"),
        ]
        client, mock = _make_client_with_mock(monkeypatch, responses)

        result = asyncio.run(client.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=4096,
        ))

        assert result == "recovered after halve"
        assert mock.calls[0]["json"]["max_tokens"] == 4096
        assert mock.calls[1]["json"]["max_tokens"] == 4096
        assert mock.calls[2]["json"]["max_tokens"] == 2048  # 减半

    def test_halve_floor_512(self, monkeypatch):
        """减半下限 512。"""
        responses = [
            httpx.TimeoutException("t1"),
            httpx.TimeoutException("t2"),
            httpx.TimeoutException("t3"),
            httpx.TimeoutException("t4"),
            _ok_response("ok"),
        ]
        client, mock = _make_client_with_mock(monkeypatch, responses)

        asyncio.run(client.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1024,
        ))

        # 第 1-2 次超时 → 第 3 次 1024//2=512；第 3-4 次超时 → 第 5 次 512//2=256 但下限 512
        assert mock.calls[2]["json"]["max_tokens"] == 512
        assert mock.calls[4]["json"]["max_tokens"] == 512  # 下限保护

    def test_old_bug_no_longer_collapses_to_512(self, monkeypatch):
        """回归：旧实现每次超时都减半，8 次重试会从 8192 崩到 512。
        新实现：8 次重试中只有每 2 次超时才减半一次，最多减半 4 次 → 8192→4096→2048→1024→512。
        但实际上：超时计数重置后若成功就停。这里测单次超时不减半。"""
        responses = [
            httpx.TimeoutException("single timeout"),
            _ok_response("ok"),
        ]
        client, mock = _make_client_with_mock(monkeypatch, responses)

        asyncio.run(client.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=8192,
        ))
        # 单次超时不应减半
        assert mock.calls[1]["json"]["max_tokens"] == 8192


# ── last_usage 提取 ─────────────────────────────────────────

class TestLastUsage:
    def test_usage_extracted_from_response(self, monkeypatch):
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        responses = [_ok_response("hi", usage=usage)]
        client, _ = _make_client_with_mock(monkeypatch, responses)

        assert client.last_usage is None  # 初始 None
        asyncio.run(client.chat(messages=[{"role": "user", "content": "hi"}]))

        assert client.last_usage == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

    def test_usage_none_when_absent(self, monkeypatch):
        data = {"choices": [{"message": {"content": "hi"}}]}  # 无 usage 字段
        responses = [MockResponse(200, data)]
        client, _ = _make_client_with_mock(monkeypatch, responses)

        asyncio.run(client.chat(messages=[{"role": "user", "content": "hi"}]))
        assert client.last_usage is None

    def test_usage_reset_on_each_call(self, monkeypatch):
        # 第 1 次有 usage，第 2 次无 → 第 2 次后 last_usage 应为 None
        r1 = _ok_response("a", usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        r2_data = {"choices": [{"message": {"content": "b"}}]}
        r2 = MockResponse(200, r2_data)
        client, _ = _make_client_with_mock(monkeypatch, [r1, r2])

        asyncio.run(client.chat(messages=[{"role": "user", "content": "x"}]))
        assert client.last_usage is not None
        asyncio.run(client.chat(messages=[{"role": "user", "content": "y"}]))
        assert client.last_usage is None


# ── 429 退避 ────────────────────────────────────────────────

class TestRateLimitBackoff:
    def test_429_then_success(self, monkeypatch):
        responses = [
            MockResponse(429),
            _ok_response("after backoff"),
        ]
        client, mock = _make_client_with_mock(monkeypatch, responses)

        # 跳过实际 sleep：用真 async no-op 替代（避免 lambda 递归）
        async def _no_sleep(*a, **kw):
            return None

        async def run():
            import agents.llm_client as lc
            monkeypatch.setattr(lc.asyncio, "sleep", _no_sleep)
            return await client.chat(messages=[{"role": "user", "content": "hi"}])

        result = asyncio.run(run())
        assert result == "after backoff"
        assert len(mock.calls) == 2


# ── 错误哨兵 ────────────────────────────────────────────────

class TestErrorSentinel:
    def test_http_500_returns_sentinel(self, monkeypatch):
        responses = [MockResponse(500)]
        client, _ = _make_client_with_mock(monkeypatch, responses)

        result = asyncio.run(client.chat(messages=[{"role": "user", "content": "hi"}]))
        assert result.startswith("[LLM API error")

    def test_unexpected_exception_returns_sentinel(self, monkeypatch):
        responses = [RuntimeError("unexpected")]
        client, _ = _make_client_with_mock(monkeypatch, responses)

        result = asyncio.run(client.chat(messages=[{"role": "user", "content": "hi"}]))
        assert result.startswith("[LLM API error")

    def test_sentinel_format(self):
        # 模板格式校验
        s = _ERROR_SENTINEL.format("test error")
        assert s == "[LLM API error: test error]"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
