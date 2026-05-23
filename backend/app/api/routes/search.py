"""
搜索引擎 API 路由

提供 SerpAPI 搜索引擎的 HTTP 查询接口。

为什么提供独立的搜索端点：
- 用户可在不启动完整分析流水线的情况下快速搜索验证
- CollectorAgent 内部复用同一个 SerpAPIService 实例
"""

from typing import Any
from fastapi import APIRouter, Depends
from app.api.responses import success_response, ResponseModel
from app.schemas.search import SearchRequest, SearchResponse
from app.services.serpapi import SerpAPIService
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()
search_service = SerpAPIService()

@router.post("/query", response_model=ResponseModel[SearchResponse])
async def execute_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await search_service.search(request)
    return success_response(data=result)
