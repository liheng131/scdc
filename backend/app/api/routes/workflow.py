"""
智能体市场洞察工作流 API

提供对话式市场洞察入口：用户提交分析主题 → 全流程自动执行 → 返回结构化报告。
"""

from typing import Any, List
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.api.deps import get_current_active_user, get_current_active_user_sse
from app.models.user import User
from app.api.responses import success_response, ResponseModel
from app.services.workflow import workflow_service

router = APIRouter()


class WorkflowStartRequest(BaseModel):
    topic: str = Field(..., max_length=500, description="分析主题或问题，例如：2025年AI芯片市场趋势")
    max_items: int = Field(default=5, ge=1, le=20, description="搜索采集的最大条目数")
    dimensions: List[str] = Field(
        default_factory=lambda: ["宏观经济环境", "行业形势与趋势", "细分板块分析", "竞争格局与对手"],
        description="自定义分析维度",
    )


@router.post("/start", response_model=ResponseModel)
async def start_workflow(
    req: WorkflowStartRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    state = workflow_service.create_workflow(
        topic=req.topic,
        max_items=req.max_items,
        dimensions=req.dimensions,
    )
    return success_response(data={
        "workflow_id": state.workflow_id,
        "topic": state.topic,
    })


@router.get("/{workflow_id}/stream")
async def stream_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_active_user_sse),
) -> StreamingResponse:
    state = workflow_service.get_workflow(workflow_id)
    if not state:
        async def err_gen():
            yield f"event: error\ndata: {{\"error\": \"Workflow not found: {workflow_id}\"}}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")
    return StreamingResponse(
        workflow_service.run_workflow_stream(state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{workflow_id}", response_model=ResponseModel)
async def get_workflow_status(
    workflow_id: str,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    state = workflow_service.get_workflow(workflow_id)
    if not state:
        return success_response(data={"error": "Workflow not found"})
    return success_response(data={
        "workflow_id": state.workflow_id,
        "topic": state.topic,
        "status": state.status,
        "current_stage": state.current_stage,
        "stages": state.stages,
        "result": state.result,
        "error": state.error,
    })


@router.get("/history/list", response_model=ResponseModel)
async def get_workflow_history(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return success_response(data=workflow_service.get_history())