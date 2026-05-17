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
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True
        )
        async def _do_fetch():
            async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
                url = f"{self.base_url}/search"
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        return await _do_fetch()

    async def search(self, request: SearchRequest) -> SearchResponse:
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

            # SearXNG number of results
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
