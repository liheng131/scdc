"""
DDGS 搜索引擎服务

封装 DuckDuckGo 搜索（DuckDuckGo Search 库，原 duckduckgo-search 已重命名为 ddgs）。
无需 API Key，免费使用，接口与原 SerpAPIService 完全一致。

为什么使用 DDGS 替代 SerpAPI：
- 完全免费，无配额限制
- 无需注册 / 配置 API Key
- 返回结构化结果，可直接映射为 SearchResultItem

为什么用 asyncio.to_thread 包装：
- ddgs 是同步库（基于 requests/curl_cffi / httpx+h2）
- 同步调用会阻塞 FastAPI 事件循环
- 放进线程池执行可并发处理多个搜索请求

为什么限制后端到 duckduckgo,wikipedia：
- ddgs 9.x 默认 auto 后端会同时向 Bing / Brave / Google / Yahoo / Yandex 等
  10+ 引擎并发请求，任一引擎因 HTTP/2 构建或反爬问题失败都可能让
  最终结果为空并抛出 "builder error"
- 仅使用 DuckDuckGo HTML 接口 + Wikipedia 接口可获得稳定结果
- 实测：auto 偶发成功、频繁 builder error；duckduckgo 100% 被 RST
  ([WinError 10054])；duckduckgo,wikipedia 是当前环境下唯一稳定子集

为什么需要重试：
- 偶发的 builder error / ConnectError / TimeoutException 通常是瞬时的，
  一次失败后立即重试大概率成功
- 最多重试 2 次（总计 3 次尝试），间隔 1 秒

为什么需要 Wikipedia 降级：
- DuckDuckGo 引擎在该环境被 TCP RST 拦截的频率很高
- 三次主后端尝试全失败时，再单独跑一次 wikipedia（不计入重试预算）
- 即使主后端 builder error，wikipedia 通常仍可访问（不同反爬策略）
"""

import asyncio
import logging
from typing import Optional

from ddgs import DDGS
from ddgs.exceptions import DDGSException, TimeoutException

from app.schemas.search import SearchRequest, SearchResultItem, SearchResponse

logger = logging.getLogger(__name__)

# 主后端：duckduckgo + wikipedia 双引擎聚合
# 严禁改为 "auto" —— auto 会触发 10+ 引擎并发，频繁 builder error
DEFAULT_BACKEND = "duckduckgo,wikipedia"

# 降级后端：主后端三次全失败时使用
FALLBACK_BACKEND = "wikipedia"

# 重试配置
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0

# 需要触发重试的异常类型（瞬时错误）
RETRYABLE_ERROR_KEYWORDS = (
    "builder error",
    "ConnectionError",
    "ConnectError",
    "RemoteProtocolError",
    "TimeoutException",
    "timed out",
    "Connection reset",
    "EOF occurred in violation of protocol",
    "No results found",  # auto 后端无结果时也常因瞬时问题导致，重试一次
)


class DDGSService:
    def __init__(self, proxy: Optional[str] = None):
        """
        :param proxy: 可选代理，形如 "socks5://user:pass@host:port"，
                      某些地区直连 DuckDuckGo 受限时使用。
                      当 proxy 为 None 时，自动从 app.core.config.settings.ddgs_proxy 读取
        """
        if proxy is None:
            try:
                from app.core.config import settings
                raw = settings.ddgs_proxy
                # 严格 trim：空字符串、纯空白都视为 None，避免 DDGS 报 "Unknown scheme for proxy URL URL('')"
                proxy = raw.strip() if raw and raw.strip() else None
            except Exception:
                # 避免循环导入或配置未就绪时崩溃
                proxy = None
        self.proxy = proxy
        self.backend = DEFAULT_BACKEND
        # 启动期自检：防止有人误把 backend 改回 "auto"
        assert self.backend != "auto", (
            "DDGSService.backend 严禁为 'auto'，auto 会触发 10+ 引擎并发并频繁 builder error"
        )

    @staticmethod
    def _map_timelimit(time_range: Optional[str]) -> Optional[str]:
        """
        将 SearchRequest.time_range (d/w/m/y) 映射为 ddgs 接受的同简写形式
        """
        if not time_range:
            return None
        mapping = {"day": "d", "week": "w", "month": "m", "year": "y"}
        return mapping.get(time_range.lower(), time_range[0].lower())

    def _is_retryable(self, err: Exception) -> bool:
        """判断异常是否属于瞬时错误，可触发重试"""
        msg = str(err) or ""
        return any(kw in msg for kw in RETRYABLE_ERROR_KEYWORDS) or isinstance(err, (TimeoutException,))

    def _do_search(self, query: str, timelimit: Optional[str], pageno: int, timeout: int, backend: Optional[str] = None) -> list:
        """
        在线程池中同步执行一次 DDGS 搜索。
        注意：每次调用都新建一个 DDGS 上下文，避免在多次重试间共享连接状态。
        """
        use_backend = backend or self.backend
        with DDGS(proxy=self.proxy, timeout=timeout, verify=False) as ddgs:
            kwargs = {
                "query": query,
                "max_results": 10,
                "page": pageno,
                "backend": use_backend,
            }
            if timelimit:
                kwargs["timelimit"] = timelimit
            return list(ddgs.text(**kwargs))

    async def _search_with_retry(
        self,
        query: str,
        timelimit: Optional[str],
        pageno: int,
        timeout: int,
        backend: Optional[str] = None,
    ) -> list:
        """
        同步执行 DDGS 搜索，遇瞬时错误自动重试。
        每次尝试前会等待一段时间，重试上限 MAX_ATTEMPTS。
        """
        last_error: Optional[Exception] = None
        use_backend = backend or self.backend
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await asyncio.to_thread(
                    self._do_search, query, timelimit, pageno, timeout, use_backend
                )
            except Exception as e:
                last_error = e
                retryable = self._is_retryable(e)
                logger.warning(
                    "DDGS search attempt %d/%d backend=%s failed (retryable=%s): %s",
                    attempt, MAX_ATTEMPTS, use_backend, retryable, e,
                )
                if not retryable or attempt >= MAX_ATTEMPTS:
                    break
                await asyncio.sleep(RETRY_DELAY_SECONDS)
        # 走到这里说明所有尝试都失败
        assert last_error is not None
        raise last_error

    async def _search_with_fallback(
        self,
        query: str,
        timelimit: Optional[str],
        pageno: int,
        timeout: int,
    ) -> tuple[list, Optional[str], Optional[str]]:
        """
        主后端重试 → 失败时使用 wikipedia 单引擎降级。
        返回 (raw_results, downgraded_flag, last_error)
        """
        try:
            results = await self._search_with_retry(
                query=query, timelimit=timelimit, pageno=pageno, timeout=timeout
            )
            return results, None, None
        except Exception as primary_error:
            # 主后端三次都失败，尝试 wikipedia 降级（不计入重试预算）
            logger.warning(
                "DDGS primary backend=%s failed after %d attempts, falling back to %s: %s",
                self.backend, MAX_ATTEMPTS, FALLBACK_BACKEND, primary_error,
            )
            try:
                results = await self._search_with_retry(
                    query=query, timelimit=timelimit, pageno=pageno, timeout=timeout,
                    backend=FALLBACK_BACKEND,
                )
                return results, FALLBACK_BACKEND, str(primary_error)
            except Exception as fallback_error:
                # 降级也失败
                return [], None, f"{primary_error} | fallback({FALLBACK_BACKEND}): {fallback_error}"

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        执行搜索并返回标准化的搜索结果。

        DDGS 参数说明：
        - query: 搜索关键词
        - max_results: 返回结果数量
        - page: 页码（1-based）
        - timelimit: 时间范围 (d/w/m/y)
        - backend: 引擎子集，默认 duckduckgo,wikipedia
        """
        timelimit = self._map_timelimit(request.time_range)

        raw_results, downgraded, primary_error = await self._search_with_fallback(
            query=request.query,
            timelimit=timelimit,
            pageno=request.pageno,
            timeout=request.timeout,
        )

        if not raw_results:
            # 全部失败
            backend_label = f"[backend={self.backend},{FALLBACK_BACKEND}-fallback]"
            err_msg = f"{backend_label} [attempt {MAX_ATTEMPTS}/{MAX_ATTEMPTS}] {primary_error}"
            logger.warning(
                "DDGS search failed for query '%s' after %d attempts last_error=%s",
                request.query, MAX_ATTEMPTS, primary_error,
            )
            record_ddgs_failure(err_msg)
            return SearchResponse(
                query=request.query,
                success=False,
                error=err_msg,
                results=[],
                total_results=0,
            )

        items: list[SearchResultItem] = []
        # 降级时结果的 source 标记为 wikipedia，否则保持 duckduckgo
        result_source = "wikipedia" if downgraded else "duckduckgo"
        for r in raw_results:
            items.append(
                SearchResultItem(
                    url=r.get("href", "") or r.get("url", ""),
                    title=r.get("title", ""),
                    snippet=r.get("body", "") or r.get("snippet", ""),
                    source=result_source,
                    score=None,
                    published_date=None,
                )
            )

        record_ddgs_success()
        if downgraded:
            logger.info(
                "DDGS search succeeded via fallback backend=%s for query '%s' (%d results)",
                FALLBACK_BACKEND, request.query, len(items),
            )

        return SearchResponse(
            query=request.query,
            success=True,
            results=items,
            total_results=len(items),
            # 如果降级成功，在 error 字段写明以便前端知晓（success=True 时仅作信息提示）
            error=f"[downgraded to {downgraded}] {primary_error}" if downgraded else None,
        )


# 模块级状态：记录最近一次健康检查结果，供 /api/v1/health/ddgs 使用
class _DDGSHealthState:
    def __init__(self) -> None:
        self.last_status: str = "unknown"  # ok | degraded | unknown
        self.last_error: Optional[str] = None
        self.last_check_at: Optional[str] = None
        self.last_engine: str = DEFAULT_BACKEND
        self._consecutive_failures: int = 0


ddgs_health = _DDGSHealthState()


def record_ddgs_success() -> None:
    """记录一次成功的 DDGS 搜索（健康状态用）"""
    from datetime import datetime, timezone
    ddgs_health.last_status = "ok"
    ddgs_health.last_error = None
    ddgs_health.last_check_at = datetime.now(timezone.utc).isoformat()
    ddgs_health._consecutive_failures = 0


def record_ddgs_failure(error: str) -> None:
    """记录一次失败的 DDGS 搜索（健康状态用）"""
    from datetime import datetime, timezone
    ddgs_health._consecutive_failures += 1
    ddgs_health.last_error = error
    ddgs_health.last_check_at = datetime.now(timezone.utc).isoformat()
    if ddgs_health._consecutive_failures >= 3:
        ddgs_health.last_status = "degraded"
    else:
        # 单次失败仍标记 ok（可能正在重试中），但 last_error 暴露给监控
        ddgs_health.last_status = ddgs_health.last_status or "unknown"
