"""
🔍 Web Search — 可插拔搜索 provider 抽象层

Provider:
- DoubaoSearchProvider: 豆包/FeedCoop 搜索 API
    endpoint: https://open.feedcoopapi.com/search_api/web_search
    auth: Bearer {APIKEY}
    body: {Query, SearchType, Count, Filter:{NeedContent, NeedUrl}, NeedSummary, ...}
    响应: 流式 NDJSON（按行迭代）
- BochaSearchProvider: 博查搜索 API（从 daily_novels/pipeline.py 抽取）
- MockSearchProvider: 无网络返回空，用于测试 / 离线降级

容错：任何 provider 异常返回空列表 + 警告日志，不阻塞主流程。
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """单条搜索结果。"""
    title: str
    snippet: str
    url: str
    source: str = ""  # provider 名，便于追溯

    def to_dict(self) -> dict:
        return {"title": self.title, "snippet": self.snippet,
                "url": self.url, "source": self.source}


class WebSearchProvider(ABC):
    """搜索 provider 抽象基类。"""

    name: str = "base"

    @abstractmethod
    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        """执行搜索，返回结果列表。失败时返回空列表（不抛异常）。"""
        ...


# ── Doubao / FeedCoop ────────────────────────────────────────────────

class DoubaoSearchProvider(WebSearchProvider):
    """豆包搜索（FeedCoop API）。

    参考 D:\\Code\\story-studio\\example\\demo_websearch_by_apikey.py
    """

    name = "doubao"
    DEFAULT_ENDPOINT = "https://open.feedcoopapi.com/search_api/web_search"

    def __init__(self, api_key: str, endpoint: str = "", timeout: float = 30.0):
        self.api_key = api_key
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            logger.warning("DoubaoSearchProvider: api_key 为空，跳过搜索")
            return []

        body = {
            "Query": query,
            "SearchType": "web",
            "Count": count,
            "Filter": {
                "NeedContent": True,
                "NeedUrl": True,
            },
            "NeedSummary": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        results: list[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", self.endpoint, headers=headers, json=body
                ) as resp:
                    if resp.status_code != 200:
                        logger.warning(
                            "Doubao search '%s' status=%d",
                            query, resp.status_code,
                        )
                        return []
                    # 流式 NDJSON：逐行解析
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        parsed = self._parse_line(line, query)
                        if parsed:
                            results.extend(parsed)
                            if len(results) >= count:
                                break
        except Exception as e:
            logger.warning("Doubao search '%s' failed: %s", query, e)
            return []

        return results[:count]

    def _parse_line(self, line: str, query: str) -> list[SearchResult]:
        """解析一行 NDJSON。FeedCoop 返回结构未严格文档化，尝试多种字段。"""
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return []

        # 整体错误响应
        if isinstance(data, dict) and data.get("error"):
            logger.warning("Doubao search error: %s", data.get("error"))
            return []

        # 可能的载荷形态：
        # 1. {"data": {"webPages": {"value": [...]}}}
        # 2. {"webPages": {"value": [...]}}
        # 3. {"results": [...]}
        # 4. {"items": [...]}
        items: list = []
        if isinstance(data, dict):
            for path in (
                ("data", "webPages", "value"),
                ("webPages", "value"),
                ("data", "results"),
                ("results",),
                ("items",),
                ("data", "items"),
            ):
                cur: Any = data
                ok = True
                for k in path:
                    if isinstance(cur, dict) and k in cur:
                        cur = cur[k]
                    else:
                        ok = False
                        break
                if ok and isinstance(cur, list):
                    items = cur
                    break
        elif isinstance(data, list):
            items = data

        out: list[SearchResult] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            title = it.get("title") or it.get("name") or ""
            snippet = it.get("snippet") or it.get("summary") or it.get("content") or ""
            url = it.get("url") or it.get("link") or ""
            if not (title or snippet or url):
                continue
            out.append(SearchResult(
                title=str(title)[:300],
                snippet=str(snippet)[:2000],
                url=str(url)[:500],
                source=self.name,
            ))
        return out


# ── Bocha ────────────────────────────────────────────────────────────

class BochaSearchProvider(WebSearchProvider):
    """博查搜索 API（从 daily_novels/pipeline.py 抽取）。"""

    name = "bocha"
    DEFAULT_ENDPOINT = "https://api.bochaai.com/v1/ai/search"

    def __init__(self, api_key: str, endpoint: str = "", timeout: float = 30.0):
        self.api_key = api_key
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            logger.warning("BochaSearchProvider: api_key 为空，跳过搜索")
            return []

        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"query": query, "count": count}
        results: list[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    self.endpoint, params=params, headers=headers, timeout=self.timeout,
                )
                if resp.status_code != 200:
                    logger.warning("Bocha search '%s' status=%d", query, resp.status_code)
                    return []
                data = resp.json()
                items = data.get("data", {}).get("webPages", {}).get("value", [])
                for r in items:
                    results.append(SearchResult(
                        title=r.get("name", ""),
                        snippet=r.get("snippet", ""),
                        url=r.get("url", ""),
                        source=self.name,
                    ))
        except Exception as e:
            logger.warning("Bocha search '%s' failed: %s", query, e)
            return []

        return results[:count]


# ── Mock ─────────────────────────────────────────────────────────────

class MockSearchProvider(WebSearchProvider):
    """无网络 / 测试用 provider，恒返回空。"""

    name = "mock"

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        logger.debug("MockSearchProvider: query='%s' (返回空)", query)
        return []


# ── 工厂 ─────────────────────────────────────────────────────────────

def get_search_provider(cfg: Any) -> WebSearchProvider:
    """根据 cfg.web_search_provider 字段工厂返回 provider 实例。

    cfg 需有：web_search_provider, web_search_api_key, web_search_endpoint
    """
    provider_name = (getattr(cfg, "web_search_provider", "mock") or "mock").lower()
    api_key = getattr(cfg, "web_search_api_key", "") or ""
    endpoint = getattr(cfg, "web_search_endpoint", "") or ""

    if provider_name == "doubao":
        return DoubaoSearchProvider(api_key, endpoint)
    if provider_name == "bocha":
        return BochaSearchProvider(api_key, endpoint)
    return MockSearchProvider()
