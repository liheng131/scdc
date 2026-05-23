"""
SerpAPI 搜索引擎服务

封装 SerpAPI 的 API 调用，为 CollectorAgent 提供搜索能力。

为什么使用 SerpAPI：
- 提供 Google 搜索结果的 API 接口，结果质量高
- 每月有免费额度（250 次），适合测试和开发
- 返回结构化 JSON 数据，易于解析
"""

import logging
import httpx
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.schemas.search import SearchRequest, SearchResultItem, SearchResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

class SerpAPIService:
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or settings.serpapi_key
        self.base_url = (base_url or "https://serpapi.com").rstrip('/')

    async def _fetch_serpapi(self, params: dict, timeout: int) -> dict:
        """
        调用 SerpAPI 并解析 JSON 响应

        为什么使用重试机制：
        - 网络波动可能导致临时失败
        - 指数退避避免频繁重试加剧服务压力
        """
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True
        )
        async def _do_fetch():
            async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
                url = f"{self.base_url}/search"
                params["api_key"] = self.api_key
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()

        return await _do_fetch()

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        执行搜索并返回标准化的搜索结果

        SerpAPI 参数说明：
        - q: 搜索查询
        - num: 返回结果数量（默认 10）
        - start: 分页起始位置
        """
        params = {
            "q": request.query,
            "num": 10,
            "start": (request.pageno - 1) * 10,
        }
        if request.time_range:
            params["tbs"] = f"qdr:{request.time_range[0]}"  # d=day, w=week, m=month, y=year

        try:
            data = await self._fetch_serpapi(params, request.timeout)
            organic_results = data.get("organic_results", [])
            items = []
            for r in organic_results:
                items.append(SearchResultItem(
                    url=r.get("link", ""),
                    title=r.get("title", ""),
                    snippet=r.get("snippet", ""),
                    source="google",
                    score=None,
                    published_date=None
                ))

            total_results = data.get("search_information", {}).get("total_results", len(items))

            return SearchResponse(
                query=request.query,
                success=True,
                results=items,
                total_results=total_results
            )
        except Exception as e:
            logger.warning(f"SerpAPI search failed for query '{request.query}': {str(e)}")
            return SearchResponse(
                query=request.query,
                success=False,
                error=str(e),
                results=[],
                total_results=0
            )
