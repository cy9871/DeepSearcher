"""搜索工具

双重搜索：DuckDuckGo（免费，默认）+ Jina Search API（可选）。
返回统一格式的搜索结果。
"""

import logging
from dataclasses import dataclass, field
from ..config import DUCKDUCKGO_ENABLED, JINA_SEARCH_ENABLED, MAX_SEARCH_RESULTS

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "duckduckgo"
    score: float = 0.0


async def search_duckduckgo(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """DuckDuckGo 搜索（免费，无需 API Key）"""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    try:
        loop = __import__('asyncio').get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: list(DDGS().text(query, max_results=max_results))
        )
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
                source="duckduckgo",
            )
            for r in results
        ]
    except (ImportError, ModuleNotFoundError):
        logger.warning("ddgs 未安装，跳过 DuckDuckGo 搜索")
        return []
    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败: {e}")
        return []


async def search_jina(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """Jina Search API（需 JINA_API_KEY）"""
    from ..config import JINA_SEARCH_API_KEY
    if not JINA_SEARCH_API_KEY:
        return []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://s.jina.ai/",
                params={"q": query, "count": max_results},
                headers={
                    "Authorization": f"Bearer {JINA_SEARCH_API_KEY}",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.warning(f"Jina Search 返回 {resp.status_code}")
                return []
            data = resp.json()
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("description", ""),
                    source="jina",
                )
                for r in data.get("data", [])
            ]
    except Exception as e:
        logger.warning(f"Jina Search 失败: {e}")
        return []


async def search(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """统一搜索入口：DDG 优先，Jina 作为补充"""
    all_results: list[SearchResult] = []
    seen_urls: set[str] = set()

    if DUCKDUCKGO_ENABLED:
        for r in await search_duckduckgo(query, max_results):
            if r.url not in seen_urls:
                all_results.append(r)
                seen_urls.add(r.url)

    # 如果 DDG 结果不足，补充 Jina
    if JINA_SEARCH_ENABLED and len(all_results) < max_results:
        for r in await search_jina(query, max_results - len(all_results)):
            if r.url not in seen_urls:
                all_results.append(r)
                seen_urls.add(r.url)

    logger.info(f"搜索 '{query}' → {len(all_results)} 条结果")
    return all_results[:max_results]


async def multi_search(queries: list[str], max_per_query: int = MAX_SEARCH_RESULTS) -> dict[str, list[SearchResult]]:
    """批量搜索"""
    import asyncio
    tasks = [search(q, max_per_query) for q in queries]
    results_list = await asyncio.gather(*tasks)
    return dict(zip(queries, results_list))
