"""
搜索引擎服务

封装 SearXNG 元搜索引擎的 API 调用，为 CollectorAgent 提供搜索能力。

为什么使用 SearXNG：
- 自托管部署，不依赖 Google/Bing 等商业 API，避免配额限制和费用
- 聚合多个搜索引擎结果，覆盖面更广
- 隐私友好，不追踪用户搜索行为
"""

import logging
import httpx
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.schemas.search import SearchRequest, SearchResultItem, SearchResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

class SearXNGService:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or settings.searxng_url).rstrip('/')

    async def _fetch_searxng(self, params: dict, timeout: int) -> dict:
        """
        调用 SearXNG API 并解析 JSON 响应

        为什么使用重试机制：
        - SearXNG 需转发请求到上游搜索引擎，网络波动可能导致临时失败
        - 指数退避避免频繁重试加剧服务压力
        """
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True
        )
        async def _do_fetch():
            headers = {
                "X-Forwarded-For": "127.0.0.1",
                "X-Real-IP": "127.0.0.1",
            }
            async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
                url = f"{self.base_url}/search"
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
        return await _do_fetch()

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        执行搜索并返回标准化的搜索结果

        为什么 format=json：
        - SearXNG 默认返回 HTML，指定 format=json 可直接获取结构化数据
        """
        params = {
            "q": request.query,
            "format": "json",
            "pageno": request.pageno,
        }
        if request.categories:
            params["categories"] = ",".join(request.categories)
        if request.time_range:
            params["time_range"] = request.time_range

        try:
            data = await self._fetch_searxng(params, request.timeout)
            raw_results = data.get("results", [])
            items = []
            for r in raw_results:
                items.append(SearchResultItem(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    snippet=r.get("content", ""),
                    source=r.get("engine", ""),
                    score=r.get("score"),
                    published_date=r.get("publishedDate")
                ))

            approx_count = data.get("number_of_results", len(items))

            return SearchResponse(
                query=request.query,
                success=True,
                results=items,
                total_results=approx_count
            )
        except Exception as e:
            logger.warning(f"SearXNG search failed for query '{request.query}': {str(e)}")
            return SearchResponse(
                query=request.query,
                success=False,
                error=str(e)
            )
