import random
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.crawlers.base import BaseCrawler
from app.schemas.crawler import CrawlRequest, CrawlResult
from app.crawlers.cleaner import HTMLCleaner

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

class HTTPCrawler(BaseCrawler):
    def __init__(self):
        self.cleaner = HTMLCleaner()

    async def _fetch_with_retry(self, url: str, timeout: int, headers: dict) -> httpx.Response:
        # Wrap async fetch with tenacity retry
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True
        )
        async def _do_fetch():
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp
        return await _do_fetch()

    async def crawl(self, request: CrawlRequest) -> CrawlResult:
        headers = request.headers or {}
        if "user-agent" not in {k.lower() for k in headers.keys()}:
            headers["User-Agent"] = random.choice(USER_AGENTS)

        try:
            response = await self._fetch_with_retry(request.url, request.timeout, headers)
            raw_html = response.text
            
            title, clean_text, metadata = "", "", {}
            if request.force_clean:
                title, clean_text, metadata = self.cleaner.clean(raw_html)

            return CrawlResult(
                url=request.url,
                success=True,
                status_code=response.status_code,
                title=title or None,
                clean_text=clean_text or None,
                raw_html=raw_html,
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"Crawler failed for {request.url} after retries: {str(e)}")
            # Fallback degradation without crashing
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            return CrawlResult(
                url=request.url,
                success=False,
                status_code=status_code,
                error=str(e)
            )
