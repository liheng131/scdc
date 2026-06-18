"""
AnySearch 搜索引擎服务

封装 AnySearch (https://api.anysearch.com/v1/search) 搜索 API。

请求格式（参考 curl 示例）：
POST {base_url}/v1/search
Headers:
  Authorization: Bearer <ANYSEARCH_API_KEY>
  Content-Type: application/json
Body:
  {
    "query": "<query>",
    "max_results": <int>,
    "domain": "<code|news|...>",  # 可选
    "tag": "<code.doc|...>",       # 可选
    "content_types": ["web","doc"] # 可选
  }

为什么用 httpx.AsyncClient：
- AnySearch 是纯 HTTP 异步 API，原生协程即可
- 项目内 notification.py / embedding.py / intent_classifier.py / agents/reporter.py
  已统一使用 httpx.AsyncClient

为什么需要重试：
- 偶发的 TimeoutException / NetworkError / 5xx 错误是瞬时的
- 最多重试 2 次（总计 3 次尝试），间隔 1 秒
- 仅对可重试状态码（408/425/429/5xx）触发重试

响应结构（实测 AnySearch 返回格式）：
{
  "code": 0,
  "message": "success",
  "data": {
    "results": [ {"title", "url", "snippet", "content"}, ... ],
    "metadata": {...}
  }
}
"""

import asyncio
import logging
from typing import Optional, Any, Dict, List

import httpx

from app.core.config import settings
from app.schemas.search import SearchRequest, SearchResultItem, SearchResponse

logger = logging.getLogger(__name__)

# 当前引擎标识（供健康检查端点返回）
DEFAULT_BACKEND = "anysearch"

# 可重试的 HTTP 状态码
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

# 重试配置
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0

# 默认每次返回结果数
DEFAULT_MAX_RESULTS = 10


class AnySearchService:
    """AnySearch 搜索引擎封装。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        :param api_key: 可选覆盖 settings.anysearch_api_key
        :param base_url: 可选覆盖 settings.anysearch_base_url
        """
        self.api_key = (api_key or settings.anysearch_api_key or "").strip()
        self.base_url = (base_url or settings.anysearch_base_url or "https://api.anysearch.com").rstrip("/")
        self.default_max_results = settings.anysearch_default_max_results or DEFAULT_MAX_RESULTS
        self.default_timeout = settings.anysearch_timeout or 10
        if not self.api_key:
            logger.warning("ANYSEARCH_API_KEY 未配置，搜索将返回错误")

    def _build_payload(self, request: SearchRequest) -> Dict[str, Any]:
        """
        构造 AnySearch 请求体。

        为什么只请求 web 类型而不带 doc：
        - 之前的 payload 会让 AnySearch 顺手把 PDF / docx 等"文档型"结果也带回来
        - 这些 doc 链接的 Content-Type 不是 text/html,crawler 当 HTML 抓后用 utf-8 解码二进制
          会得到 `%PDF-1.3 % 10 obj <> endobj ...` 这种乱码进入 LLM 上下文
        - 显式限定 content_types=["web"] 可在源头避免
        """
        return {
            "query": request.query,
            "max_results": self.default_max_results,
            "content_types": ["web"],
        }

    async def _do_request(self, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        """发起单次 AnySearch HTTP POST 请求并返回 JSON 响应。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/v1/search"
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in RETRYABLE_STATUS:
                # 抛错以触发重试
                resp.raise_for_status()
            if resp.status_code >= 400:
                # 非可重试错误：直接抛错
                raise httpx.HTTPStatusError(
                    f"AnySearch HTTP {resp.status_code}: {resp.text[:200]}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()

    def _is_retryable(self, err: Exception) -> bool:
        """判断异常是否属于瞬时错误，可触发重试。"""
        if isinstance(err, (httpx.TimeoutException, httpx.NetworkError)):
            return True
        if isinstance(err, httpx.HTTPStatusError) and err.response is not None:
            return err.response.status_code in RETRYABLE_STATUS
        return False

    async def _search_with_retry(
        self,
        payload: Dict[str, Any],
        timeout: int,
    ) -> List[Dict[str, Any]]:
        """
        发起搜索请求，遇瞬时错误自动重试。
        重试上限 MAX_ATTEMPTS。
        返回原始结果列表（未映射为 SearchResultItem）。

        响应结构（实测 AnySearch 返回格式）：
        {
          "code": 0,
          "message": "success",
          "data": {
            "results": [ {...}, {...} ],
            "metadata": {...}
          }
        }

        兼容其它常见变体：
        - {"results": [...]} 直接挂在顶层
        - {"data": [...]} data 直接是列表
        - 顶层就是 list
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                data = await self._do_request(payload, timeout)
                return self._extract_results(data)
            except Exception as e:
                last_error = e
                retryable = self._is_retryable(e)
                logger.warning(
                    "AnySearch attempt %d/%d failed (retryable=%s): %s",
                    attempt, MAX_ATTEMPTS, retryable, e,
                )
                if not retryable or attempt >= MAX_ATTEMPTS:
                    break
                await asyncio.sleep(RETRY_DELAY_SECONDS)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _extract_results(data: Any) -> List[Dict[str, Any]]:
        """
        从 AnySearch 响应中提取结果列表。
        优先处理实测的 {"code":0,"message":"success","data":{"results":[...]}} 结构。
        """
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if not isinstance(data, dict):
            return []
        # 校验业务状态码（非 0 视为错误，返回空让上层报错）
        code = data.get("code")
        if code is not None and code != 0:
            raise RuntimeError(
                f"AnySearch business error: code={code}, message={data.get('message', '')}"
            )
        # 1) 嵌套 data.results（实测格式）
        inner = data.get("data")
        if isinstance(inner, dict):
            results = inner.get("results")
            if isinstance(results, list):
                return [x for x in results if isinstance(x, dict)]
        # 2) 顶层 data 为列表
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
        # 3) 顶层 results
        results = data.get("results")
        if isinstance(results, list):
            return [x for x in results if isinstance(x, dict)]
        return []

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        执行搜索并返回标准化的搜索结果。

        AnySearch 参数说明：
        - query: 搜索关键词
        - max_results: 返回结果数量（默认 10，由 settings.anysearch_default_max_results 控制）
        """
        if not self.api_key:
            return SearchResponse(
                query=request.query,
                success=False,
                error="ANYSEARCH_API_KEY 未配置",
                results=[],
                total_results=0,
            )

        payload = self._build_payload(request)
        timeout = min(request.timeout or self.default_timeout, 30)

        try:
            raw_results = await self._search_with_retry(payload, timeout)
        except Exception as e:
            err_msg = f"[engine=anysearch] [attempt {MAX_ATTEMPTS}/{MAX_ATTEMPTS}] {e}"
            logger.warning(
                "AnySearch search failed for query '%s' after %d attempts last_error=%s",
                request.query, MAX_ATTEMPTS, e,
            )
            record_anysearch_failure(err_msg)
            return SearchResponse(
                query=request.query,
                success=False,
                error=err_msg,
                results=[],
                total_results=0,
            )

        items: List[SearchResultItem] = []
        for r in raw_results:
            if not isinstance(r, dict):
                continue
            items.append(
                SearchResultItem(
                    url=r.get("url") or r.get("link") or "",
                    title=r.get("title") or "",
                    snippet=(
                        r.get("snippet")
                        or r.get("content")
                        or r.get("description")
                        or ""
                    ),
                    source=r.get("source") or "anysearch",
                    score=r.get("score"),
                    published_date=r.get("published_date") or r.get("date"),
                )
            )

        record_anysearch_success()
        logger.info(
            "AnySearch search succeeded for query '%s' (%d results)",
            request.query, len(items),
        )

        return SearchResponse(
            query=request.query,
            success=True,
            results=items,
            total_results=len(items),
        )

    async def search_multi_categories(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        max_per_category: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> SearchResponse:
        """
        按多个类别并发搜索，合并去重后返回。

        为什么用并发搜索：
        - 不同类别（通用/新闻/科技）覆盖不同来源，丰富数据多样性
        - asyncio.gather 并发执行，总耗时不增加（取最慢的那次）

        categories: 搜索类别列表，如 ["", "news", "tech"]
          - 空字符串表示通用搜索（不指定 domain）
          - 其他值对应 AnySearch 的 domain 参数
        max_per_category: 每个类别最大返回数
        timeout: 单次搜索超时
        """
        if not self.api_key:
            return SearchResponse(
                query=query, success=False, error="ANYSEARCH_API_KEY 未配置", results=[], total_results=0,
            )

        categories = categories or [""]  # 默认仅通用搜索
        max_per_category = max_per_category or self.default_max_results
        timeout = min(timeout or self.default_timeout, 30)

        # 并发执行多类别搜索
        tasks = []
        for cat in categories:
            payload = {
                "query": query,
                "max_results": max_per_category,
                "content_types": ["web"],
            }
            if cat:  # 仅当指定类别时添加 domain 参数
                payload["domain"] = cat
            tasks.append(self._search_with_retry(payload, timeout))

        results_by_category = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果并去重（按 URL 去重）
        seen_urls: set = set()
        merged_items: List[SearchResultItem] = []
        for result in results_by_category:
            if isinstance(result, Exception):
                logger.warning("Multi-category search failed for one category: %s", result)
                continue
            for item in result:
                url = item.get("url") or item.get("link") or ""
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    merged_items.append(SearchResultItem(
                        url=url,
                        title=item.get("title") or "",
                        snippet=(
                            item.get("snippet")
                            or item.get("content")
                            or item.get("description")
                            or ""
                        ),
                        source=item.get("source") or "anysearch",
                        score=item.get("score"),
                        published_date=item.get("published_date") or item.get("date"),
                    ))

        record_anysearch_success()
        logger.info(
            "AnySearch multi-category search succeeded for query '%s' (%d categories, %d merged results)",
            query, len(categories), len(merged_items),
        )

        return SearchResponse(
            query=query, success=True, results=merged_items, total_results=len(merged_items),
        )


# 模块级状态：记录最近一次健康检查结果，供 /api/v1/health/anysearch 使用
class _AnySearchHealthState:
    def __init__(self) -> None:
        self.last_status: str = "unknown"  # ok | degraded | unknown
        self.last_error: Optional[str] = None
        self.last_check_at: Optional[str] = None
        self.last_engine: str = DEFAULT_BACKEND
        self._consecutive_failures: int = 0


anysearch_health = _AnySearchHealthState()


def record_anysearch_success() -> None:
    """记录一次成功的 AnySearch 搜索（健康状态用）"""
    from datetime import datetime, timezone
    anysearch_health.last_status = "ok"
    anysearch_health.last_error = None
    anysearch_health.last_check_at = datetime.now(timezone.utc).isoformat()
    anysearch_health._consecutive_failures = 0


def record_anysearch_failure(error: str) -> None:
    """记录一次失败的 AnySearch 搜索（健康状态用）"""
    from datetime import datetime, timezone
    anysearch_health._consecutive_failures += 1
    anysearch_health.last_error = error
    anysearch_health.last_check_at = datetime.now(timezone.utc).isoformat()
    if anysearch_health._consecutive_failures >= 3:
        anysearch_health.last_status = "degraded"
    else:
        # 单次失败仍标记 ok（可能正在重试中），但 last_error 暴露给监控
        anysearch_health.last_status = anysearch_health.last_status or "unknown"
