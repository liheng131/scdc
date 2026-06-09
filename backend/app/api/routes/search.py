"""
搜索引擎 API 路由

提供 AnySearch 搜索引擎的 HTTP 查询接口。

为什么提供独立的搜索端点：
- 用户可在不启动完整分析流水线的情况下快速搜索验证
- CollectorAgent 内部复用同一个 AnySearchService 实例
"""

from typing import Any
from fastapi import APIRouter, Depends
from app.api.responses import success_response, ResponseModel
from app.schemas.search import SearchRequest, SearchResponse
from app.services.anysearch import AnySearchService, anysearch_health, DEFAULT_BACKEND
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()
search_service = AnySearchService()


@router.post("/query", response_model=ResponseModel[SearchResponse])
async def execute_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await search_service.search(request)
    return success_response(data=result)


@router.get("/health/anysearch", response_model=ResponseModel)
async def anysearch_health_check(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    AnySearch 健康检查端点（路径：/api/v1/search/health/anysearch）
    兼容通过 /api/v1/health/anysearch 直接访问的实现见 api_router 的转发
    """
    probe = await search_service.search(SearchRequest(query="ping", timeout=5))

    payload = {
        "status": "ok" if probe.success else "degraded",
        "engine": DEFAULT_BACKEND,
        "effective_api_url": search_service.base_url,
        "api_key_set": bool(search_service.api_key),
        "last_check_at": anysearch_health.last_check_at,
        "last_error": anysearch_health.last_error,
        "consecutive_failures": anysearch_health._consecutive_failures,
        "probe": {
            "success": probe.success,
            "result_count": probe.total_results,
            "error": probe.error,
        },
    }
    return success_response(data=payload)
