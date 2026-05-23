"""
任务触发 API 路由

提供同步和 SSE 流式两种方式触发 AI 分析流水线。

为什么同时提供两种模式：
- /qa（同步）：适合简单场景，一次请求完成全部分析并返回报告
- /qa/stream（SSE 流式）：前端可实时展示各阶段进度，增强用户体验
  每个阶段完成后向客户端推送 event: stage_update，前端据此更新进度条
"""

from typing import Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.services.trigger import TriggerService

router = APIRouter()
trigger_service = TriggerService()

class QARequest(BaseModel):
    topic: str = Field(..., max_length=200)
    max_items: int = Field(default=2, le=10)

@router.post("/qa", response_model=ResponseModel)
async def trigger_qa_sync(
    req: QARequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    result = await trigger_service.run_qa_sync(session, req.topic, req.max_items, current_user.id)
    return success_response(data=result)

@router.get("/qa/stream")
async def trigger_qa_stream(
    topic: str,
    max_items: int = 2,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    generator = trigger_service.run_qa_stream(session, topic, max_items, current_user.id)
    return StreamingResponse(generator, media_type="text/event-stream")
