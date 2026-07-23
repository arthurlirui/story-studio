"""单元测试：agents/web_search.py 的 provider 抽象层。

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 手动驱动 async 用例。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agents.web_search import (
    BochaSearchProvider, DoubaoSearchProvider, MockSearchProvider,
    SearchResult, WebSearchProvider, get_search_provider,
)


def _run(coro):
    """新建 event loop 跑完协程，替代 pytest-asyncio。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSearchResult:
    def test_to_dict(self):
        r = SearchResult(title="t", snippet="s", url="u", source="doubao")
        assert r.to_dict() == {
            "title": "t", "snippet": "s", "url": "u", "source": "doubao",
        }


class TestMockSearchProvider:
    def test_returns_empty(self):
        p = MockSearchProvider()
        assert _run(p.search("anything")) == []


class _FakeAsyncCtx:
    """模拟 httpx.AsyncClient 的 async context manager 行为（stream 调用）。"""

    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *exc):
        return False


class _FakeAsyncClientFactory:
    """patch httpx.AsyncClient 的替身：每次调用返回 _FakeAsyncCtx。
    保留以兼容旧的 stream() 风格测试；现在 provider 用 _get_client 复用，
    新测试直接注入 p._client 即可。
    """

    def __init__(self, client):
        self.client = client

    def __call__(self, *args, **kwargs):
        return _FakeAsyncCtx(self.client)


class TestBochaSearchProvider:
    def test_empty_api_key_returns_empty(self):
        p = BochaSearchProvider(api_key="")
        assert _run(p.search("q")) == []

    def test_parses_webpages(self):
        p = BochaSearchProvider(api_key="k")
        mock_payload = {
            "data": {
                "webPages": {
                    "value": [
                        {"name": "Title1", "snippet": "Snippet1", "url": "http://a"},
                        {"name": "Title2", "snippet": "Snippet2", "url": "http://b"},
                    ]
                }
            }
        }
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_payload

        async def fake_get(*a, **kw):
            return resp

        client.get = fake_get
        # M1-web_search: provider 现在复用 _client，直接注入 fake client
        p._client = client
        results = _run(p.search("query", count=5))

        assert len(results) == 2
        assert results[0].title == "Title1"
        assert results[0].url == "http://a"
        assert results[0].source == "bocha"

    def test_http_error_returns_empty(self):
        p = BochaSearchProvider(api_key="k")
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 500

        async def fake_get(*a, **kw):
            return resp

        client.get = fake_get
        p._client = client
        assert _run(p.search("q")) == []

    def test_exception_returns_empty(self):
        p = BochaSearchProvider(api_key="k")

        class _ExplodingClient:
            async def get(self, *a, **kw):
                raise Exception("boom")

        p._client = _ExplodingClient()
        assert _run(p.search("q")) == []


class TestDoubaoSearchProvider:
    def test_empty_api_key_returns_empty(self):
        p = DoubaoSearchProvider(api_key="")
        assert _run(p.search("q")) == []

    def test_default_endpoint(self):
        p = DoubaoSearchProvider(api_key="k")
        assert "feedcoopapi.com" in p.endpoint

    def test_custom_endpoint(self):
        p = DoubaoSearchProvider(api_key="k", endpoint="https://custom.example.com/s")
        assert p.endpoint == "https://custom.example.com/s"

    def test_parse_line_handles_webpages(self):
        p = DoubaoSearchProvider(api_key="k")
        line = '{"data": {"webPages": {"value": [{"title": "t", "snippet": "s", "url": "u"}]}}}'
        out = p._parse_line(line, "q")
        assert len(out) == 1
        assert out[0].title == "t"
        assert out[0].source == "doubao"

    def test_parse_line_handles_invalid_json(self):
        p = DoubaoSearchProvider(api_key="k")
        assert p._parse_line("not json", "q") == []

    def test_parse_line_handles_error(self):
        p = DoubaoSearchProvider(api_key="k")
        assert p._parse_line('{"error": "invalid_request"}', "q") == []

    def test_parse_line_handles_flat_list(self):
        p = DoubaoSearchProvider(api_key="k")
        line = '[{"title": "t1", "url": "u1"}, {"title": "t2", "url": "u2"}]'
        out = p._parse_line(line, "q")
        assert len(out) == 2


class _FakeStreamResponse:
    """模拟 httpx client.stream() 返回的 async context manager。"""

    def __init__(self, status_code: int, lines: list[str]):
        self.status_code = status_code
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamClient:
    """模拟 httpx.AsyncClient，stream() 返回 _FakeStreamResponse。"""

    def __init__(self, resp: _FakeStreamResponse):
        self._resp = resp
        self.stream_calls: list[tuple] = []

    def stream(self, method, url, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return _FakeStreamCtx(self._resp)

    async def aclose(self):
        pass


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class TestDoubaoSearchStreaming:
    """Doubao search 的流式 NDJSON 解析流程。"""

    def test_parses_streaming_lines(self):
        """多行 NDJSON 应全部解析为 SearchResult。"""
        p = DoubaoSearchProvider(api_key="k")
        lines = [
            '{"data": {"webPages": {"value": [{"title": "t1", "snippet": "s1", "url": "u1"}]}}}',
            '{"data": {"webPages": {"value": [{"title": "t2", "snippet": "s2", "url": "u2"}]}}}',
        ]
        resp = _FakeStreamResponse(200, lines)
        client = _FakeStreamClient(resp)
        p._client = client

        results = _run(p.search("query", count=5))
        assert len(results) == 2
        assert results[0].title == "t1"
        assert results[1].title == "t2"
        assert all(r.source == "doubao" for r in results)

    def test_breaks_at_count(self):
        """结果数达到 count 时应提前 break，不消费后续行。"""
        p = DoubaoSearchProvider(api_key="k")
        lines = [
            '{"webPages": {"value": [{"title": "t1", "url": "u1"}, {"title": "t2", "url": "u2"}]}}',
            '{"webPages": {"value": [{"title": "t3", "url": "u3"}, {"title": "t4", "url": "u4"}]}}',
        ]
        resp = _FakeStreamResponse(200, lines)
        client = _FakeStreamClient(resp)
        p._client = client

        results = _run(p.search("query", count=2))
        # 第一行已返回 2 条，应在达到 count 后 break
        assert len(results) == 2
        assert results[0].title == "t1"
        assert results[1].title == "t2"

    def test_non_200_returns_empty(self):
        """非 200 状态码应返回空列表。"""
        p = DoubaoSearchProvider(api_key="k")
        resp = _FakeStreamResponse(404, [])
        client = _FakeStreamClient(resp)
        p._client = client

        results = _run(p.search("query", count=5))
        assert results == []

    def test_exception_returns_empty(self):
        """stream 过程中异常应返回空列表（不抛异常）。"""
        p = DoubaoSearchProvider(api_key="k")

        class _ExplodingStreamClient:
            def stream(self, method, url, **kwargs):
                return _ExplodingStreamCtx()

            async def aclose(self):
                pass

        class _ExplodingStreamCtx:
            async def __aenter__(self):
                raise RuntimeError("stream boom")

            async def __aexit__(self, *exc):
                return False

        p._client = _ExplodingStreamClient()
        results = _run(p.search("query", count=5))
        assert results == []


class TestGetSearchProvider:
    def test_doubao(self):
        cfg = SimpleNamespace(
            web_search_provider="doubao",
            web_search_api_key="k", web_search_endpoint="",
        )
        p = get_search_provider(cfg)
        assert isinstance(p, DoubaoSearchProvider)

    def test_bocha(self):
        cfg = SimpleNamespace(
            web_search_provider="bocha",
            web_search_api_key="k", web_search_endpoint="",
        )
        p = get_search_provider(cfg)
        assert isinstance(p, BochaSearchProvider)

    def test_mock(self):
        cfg = SimpleNamespace(
            web_search_provider="mock",
            web_search_api_key="", web_search_endpoint="",
        )
        p = get_search_provider(cfg)
        assert isinstance(p, MockSearchProvider)

    def test_unknown_falls_back_to_mock(self):
        cfg = SimpleNamespace(
            web_search_provider="unknown_xyz",
            web_search_api_key="", web_search_endpoint="",
        )
        p = get_search_provider(cfg)
        assert isinstance(p, MockSearchProvider)

    def test_missing_attr_falls_back_to_mock(self):
        cfg = SimpleNamespace()
        p = get_search_provider(cfg)
        assert isinstance(p, MockSearchProvider)
