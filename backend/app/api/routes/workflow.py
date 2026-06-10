"""
智能体市场洞察工作流 API

提供对话式市场洞察入口：用户提交分析主题 → 全流程自动执行 → 返回结构化报告。
"""

from typing import Any, List, Literal, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.api.deps import get_current_active_user, get_current_active_user_sse
from app.models.user import User
from app.api.responses import success_response, ResponseModel
from app.services.workflow import workflow_service
from app.core.runtime_config import rumtime_config

router = APIRouter()


def _resolve_use_rag(req_use_rag: bool) -> bool:
    """合并请求参数与系统配置。请求体 True 优先；否则读取 rumtime_config.direct_response_rag。"""
    if req_use_rag:
        return True
    try:
        return bool(rumtime_config.get("direct_response_rag", False))
    except Exception:
        return False


class WorkflowStartRequest(BaseModel):
    topic: str = Field(..., max_length=500, description="分析主题或问题，例如：2025年AI芯片市场趋势")
    max_items: int = Field(default=5, ge=1, le=20, description="搜索采集的最大条目数")
    dimensions: List[str] = Field(
        default_factory=lambda: ["宏观经济环境", "行业形势与趋势", "细分板块分析", "竞争格局与对手"],
        description="自定义分析维度",
    )
    use_rag: bool = Field(default=False, description="直答时是否启用历史报告 RAG 检索")


class FollowUpRequest(BaseModel):
    message: str = Field(..., description="追问消息内容")
    conversation_history: List[dict] = Field(
        default_factory=list,
        description="之前的对话历史，每个元素包含 role 和 content",
    )
    use_rag: bool = Field(default=False, description="直答时是否启用历史报告 RAG 检索")


class ReentryRequest(BaseModel):
    target_stage: str = Field(..., description="目标阶段: collecting, analyzing, reporting")
    user_feedback: str = Field(default="", description="用户补充反馈/约束")


# --- Phase 2 Human-in-the-Loop (Spec 1) ---
class ConfirmStageRequest(BaseModel):
    """阶段确认请求

    decision=accept → 进入下一阶段
    decision=reject → 重跑当前阶段
        user_edits  非空 → 与原 topic 合并后重跑
        user_feedback 非空 → AI 解析后调整策略重跑
        两者都为空 → 完全重跑
    """
    decision: Literal["accept", "reject"]
    user_edits: Optional[dict] = Field(
        default=None,
        description="用户编辑（如 extra_urls/extra_keywords）",
    )
    user_feedback: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="用户文字反馈",
    )


class WorkflowStatusResponse(BaseModel):
    run_id: str
    stage: str
    stage_state: str
    stage_output: Optional[dict] = None
    stage_history: Optional[list] = None


@router.post("/start")
async def start_workflow(
    req: WorkflowStartRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    effective_use_rag = _resolve_use_rag(req.use_rag)
    decision = await workflow_service.master_agent.process_message(
        req.topic,
        use_rag=effective_use_rag,
    )

    if decision.action == "direct":
        state = await workflow_service.create_workflow(
            topic=req.topic,
            max_items=0,
            dimensions=[],
            use_rag=effective_use_rag,
        )
        state.is_direct_response = True
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "is_direct_response": True,
        })

    if decision.action == "reentry":
        state = await workflow_service.create_workflow(
            topic=req.topic,
            max_items=req.max_items,
            dimensions=req.dimensions,
            use_rag=effective_use_rag,
        )
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "intent_type": decision.intent_type,
            "target_stage": decision.target_stage,
            "user_feedback": decision.user_feedback or "",
        })

    # decision.action == "orchestrate"（启动完整四阶段工作流）
    state = await workflow_service.create_workflow(
        topic=req.topic,
        max_items=req.max_items,
        dimensions=req.dimensions,
        use_rag=effective_use_rag,
    )
    return success_response(data={
        "workflow_id": state.workflow_id,
        "topic": state.topic,
    })


@router.post("/follow-up")
async def follow_up_workflow(
    req: FollowUpRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    effective_use_rag = _resolve_use_rag(req.use_rag)
    decision = await workflow_service.master_agent.process_message(
        req.message,
        conversation_history=req.conversation_history,
        use_rag=effective_use_rag,
        has_existing_report=True,
    )

    if decision.action == "orchestrate":
        state = await workflow_service.create_workflow(
            topic=req.message,
            max_items=5,
            dimensions=["宏观经济环境", "行业形势与趋势", "细分板块分析", "竞争格局与对手"],
            conversation_history=req.conversation_history,
            use_rag=effective_use_rag,
        )
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "intent_type": decision.intent_type,
        })

    if decision.action == "reentry":
        state = await workflow_service.create_workflow(
            topic=req.message,
            max_items=5,
            dimensions=[],
            conversation_history=req.conversation_history,
            use_rag=effective_use_rag,
        )
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "intent_type": decision.intent_type,
            "target_stage": decision.target_stage,
            "user_feedback": decision.user_feedback or "",
        })

    # decision.action == "direct"（追问为常规问题，走直答流）
    state = await workflow_service.create_workflow(
        topic=req.message,
        max_items=0,
        dimensions=[],
        conversation_history=req.conversation_history,
        use_rag=effective_use_rag,
    )
    state.is_direct_response = True
    return success_response(data={
        "workflow_id": state.workflow_id,
        "topic": state.topic,
        "intent_type": decision.intent_type,
    })


@router.get("/{workflow_id}/stream")
async def stream_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_active_user_sse),
) -> StreamingResponse:
    state = await workflow_service.get_workflow(workflow_id)
    if not state:
        async def err_gen():
            yield f"event: error\ndata: {{\"error\": \"Workflow not found: {workflow_id}\"}}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")
    return StreamingResponse(
        workflow_service.run_workflow_stream(state, use_rag=state.use_rag),
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
    state = await workflow_service.get_workflow(workflow_id)
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


@router.post("/{workflow_id}/reentry")
async def reentry_workflow(
    workflow_id: str,
    req: ReentryRequest,
    current_user: User = Depends(get_current_active_user_sse),
) -> StreamingResponse:
    original_state = await workflow_service.get_workflow(workflow_id)
    if not original_state:
        async def err_gen():
            yield f"event: error\ndata: {{\"error\": \"Workflow not found: {workflow_id}\"}}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    topic = original_state.topic
    return StreamingResponse(
        workflow_service.run_reentry_stream(
            original_workflow_id=workflow_id,
            target_stage=req.target_stage,
            user_feedback=req.user_feedback,
            topic=topic,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/list", response_model=ResponseModel)
async def get_workflow_history(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return success_response(data=await workflow_service.get_history())