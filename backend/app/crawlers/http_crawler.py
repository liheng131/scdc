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
        带指数退避重试的 HTTP GET 请求。

        为什么使用 tenacity 而不是手动实现重试：
        - tenacity 支持多种重试策略组合（次数/间隔/异常类型）
        - 内置 jitter 避免"惊群效应"（多个重试请求同时到达服务端）
        - follow_redirects=True 自动处理 301/302 跳转

        重试策略（Phase 7 修复）：
        - 4xx 客户端错误（含 403 反爬、404 失效、401 未授权）不重试——这是终态,不是瞬态
        - 5xx 服务器错误、httpx.RequestError（网络瞬态）才重试 3 次
        - 旧版 4xx 也会重试,导致 gminsights 等反爬站每个 URL 多花 7+ 秒
        """
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            # 重试条件:httpx.HTTPError(基类)同时覆盖
            #   - RequestError(子类):网络级瞬态错误 ConnectError/TimeoutException/...
            #   - HTTPStatusError(子类):5xx 服务端错误
            # 注意:这里 HTTPStatusError 实际上只会由 5xx 触发,因为 4xx 在内部就 return 了
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True
        )
        async def _do_fetch():
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                # 4xx 终态:不重试,直接返回让上层走 snippet 降级
                if 400 <= resp.status_code < 500:
                    return resp
                # 5xx 才 raise_for_status → HTTPStatusError → tenacity 重试
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

            # 1) Content-Type 早拒:非 HTML/XML 的响应直接失败,让 collector 走 snippet 降级
            #    避免 PDF / 图片 / 视频 / 二进制被 utf-8 解码成乱码后进 LLM 上下文
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not any(
                ok in content_type for ok in ("text/html", "application/xhtml", "text/xml", "application/xml", "text/plain")
            ):
                logger.info(
                    f"Skip non-HTML content-type for {request.url}: {content_type}"
                )
                return CrawlResult(
                    url=request.url,
                    success=False,
                    status_code=response.status_code,
                    error=f"unsupported content-type: {content_type}",
                )

            # 2) Magic byte 兜底:Content-Type 缺失/被伪装时仍能识别 PDF 等二进制
            #    %PDF-1.x 是 PDF 头;PK\x03\x04 是 zip/docx/xlsx 等 OOXML 头
            head_bytes = response.content[:8]
            if head_bytes[:4] == b"%PDF" or head_bytes[:2] == b"PK":
                logger.info(
                    f"Skip binary file detected by magic bytes for {request.url}: {head_bytes[:8]!r}"
                )
                return CrawlResult(
                    url=request.url,
                    success=False,
                    status_code=response.status_code,
                    error=f"binary file detected (magic={head_bytes[:4]!r})",
                )

            raw_html = response.text

            # 4xx 响应:body 可能是 Cloudflare challenge 页/错误页,即使有 HTML 也不应被
            # 当成有效内容。让 collector 走 snippet 降级。
            if 400 <= response.status_code < 500:
                logger.info(
                    f"4xx response for {request.url}: status={response.status_code}, falling back to snippet"
                )
                return CrawlResult(
                    url=request.url,
                    success=False,
                    status_code=response.status_code,
                    error=f"HTTP {response.status_code}",
                )

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


            