"""
HTTP 网页爬虫

通过 HTTP 请求获取网页内容，支持自动清洗和指数退避重试。

为什么轮换 User-Agent：
- 许多网站对所有请求使用同一 UA 的客户端会触发反爬机制
- 3 个主流浏览器 UA 轮换模拟真实用户行为，降低拦截概率

为什么 verify=False：
- 部分内部网站使用自签名 SSL 证书，验证会导致连接失败
- 在生产环境中（爬取的 URL 可控）是可接受的安全权衡
"""

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
        """
        带指数退避重试的 HTTP GET 请求

        为什么使用 tenacity 而不是手动实现重试：
        - tenacity 支持多种重试策略组合（次数/间隔/异常类型）
        - 内置 jitter 避免"惊群效应"（多个重试请求同时到达服务端）
        - follow_redirects=True 自动处理 301/302 跳转
        """
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
        """
        执行网页爬取

        force_clean 选项说明：
        - 当 CollectorAgent 需要提取纯文本用于 LLM 分析时设为 True
        - 当只需要获取原始 HTML（如用于归档）时设为 False
        """
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
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            return CrawlResult(
                url=request.url,
                success=False,
                status_code=status_code,
                error=str(e)
            )
