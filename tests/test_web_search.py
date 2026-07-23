"""单元测试：agents/web_search.py 的 provider 抽象层。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agents.web_search import (
    BochaSearchProvider, DoubaoSearchProvider, MockSearchProvider,
    SearchResult, WebSearchProvider, get_search_provider,
)


class TestSearchResult:
    def test_to_dict(self):
        r = SearchResult(title="t", snippet="s", url="u", source="doubao")
        assert r.to_dict() == {
            "title": "t", "snippet": "s", "url": "u", "source": "doubao",
        }


class TestMockSearchProvider:
    @pytest.mark.asyncio
    async def test_returns_empty(self):
        p = MockSearchProvider()
        assert await p.search("anything") == []


class TestBochaSearchProvider:
    @pytest.mark.asyncio
    async def test_empty_api_key_returns_empty(self):
        p = BochaSearchProvider(api_key="")
        assert await p.search("q") == []

    @pytest.mark.asyncio
    async def test_parses_webpages(self):
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
        with patch("agents.web_search.httpx.AsyncClient") as mock_client_cls:
            client = MagicMock()
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = mock_payload
            client.get = AsyncMock(return_value=resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            results = await p.search("query", count=5)

        assert len(results) == 2
        assert results[0].title == "Title1"
        assert results[0].url == "http://a"
        assert results[0].source == "bocha"

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self):
        p = BochaSearchProvider(api_key="k")
        with patch("agents.web_search.httpx.AsyncClient") as mock_client_cls:
            client = MagicMock()
            resp = MagicMock()
            resp.status_code = 500
            client.get = AsyncMock(return_value=resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            assert await p.search("q") == []

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self):
        p = BochaSearchProvider(api_key="k")
        with patch("agents.web_search.httpx.AsyncClient", side_effect=Exception("boom")):
            assert await p.search("q") == []


class TestDoubaoSearchProvider:
    @pytest.mark.asyncio
    async def test_empty_api_key_returns_empty(self):
        p = DoubaoSearchProvider(api_key="")
        assert await p.search("q") == []

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
