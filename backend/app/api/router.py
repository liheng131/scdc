"""
API 路由聚合模块

职责：
- 创建顶层 APIRouter 实例
- 统一注册所有业务子路由到 /api/v1 前缀下（由 main.py 挂载）
- 内置健康检查端点（/api/v1/health），用于负载均衡探测和运行状态监控
"""

from fastapi import APIRouter, Depends
from app.api.responses import success_response, ResponseModel
from app.api.routes import auth, data_sources, collected_records, parsers, crawlers, search, agents, tasks, triggers, schedules, events, notifications, reports, workflow, settings, metrics
from app.services.anysearch import AnySearchService, anysearch_health, DEFAULT_BACKEND
from app.schemas.search import SearchRequest
from app.api.deps import get_current_active_user
from app.models.user import User

# 顶层路由实例，所有业务模块的子路由都注册到此处
api_router = APIRouter()

# ===== 业务路由注册 =====
# 每个子模块使用独立的 prefix 和 OpenAPI tag，便于 Swagger UI 分组展示
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(data_sources.router, prefix="/data-sources", tags=["data-sources"])
api_router.include_router(collected_records.router, prefix="/data-sources", tags=["collected-records"])
api_router.include_router(parsers.router, prefix="/parsers", tags=["parsers"])
api_router.include_router(crawlers.router, prefix="/crawlers", tags=["crawlers"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(triggers.router, prefix="/triggers", tags=["triggers"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(metrics.router, prefix="/metrics-json", tags=["metrics"])

# 共享一个 AnySearchService 实例给健康检查用
_anysearch_probe = AnySearchService()

@api_router.get("/health", response_model=ResponseModel)
async def health_check():
    """
    健康检查端点

    用途：
    - Docker 容器健康探测（HEALTHCHECK）
    - 负载均衡器（Nginx）的服务可用性检查
    - 返回版本号和环境标识，方便运维排查
    """
    from app.core.config import settings
    return success_response(data={"version": "1.0.0", "environment": settings.app_env})


@api_router.get("/health/anysearch", response_model=ResponseModel)
async def anysearch_health_check(
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    AnySearch 搜索服务健康检查端点（路径：/api/v1/health/anysearch）

    主动执行一次轻量搜索（query="ping", max_results=1）探测 AnySearch 可用性，
    返回最近一次搜索的状态、最近错误、引擎配置等诊断信息。
    """
    probe = await _anysearch_probe.search(SearchRequest(query="ping", timeout=5))

    payload = {
        "status": "ok" if probe.success else "degraded",
        "engine": DEFAULT_BACKEND,
        "effective_api_url": _anysearch_probe.base_url,
        "api_key_set": bool(_anysearch_probe.api_key),
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