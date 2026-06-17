"""
智能体市场洞察工作流 API

提供对话式市场洞察入口：用户提交分析主题 → 全流程自动执行 → 返回结构化报告。
"""

import logging
from dataclasses import replace
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.api.deps import get_current_active_user, get_current_active_user_sse
from app.models.user import User
from app.api.responses import success_response, ResponseModel
from app.services.workflow import workflow_service, STAGE_SEQUENCE
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)
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
    max_items: int = Field(default=10, ge=1, le=50, description="搜索采集的最大条目数")
    dimensions: List[str] = Field(
        default_factory=list,
        description="自定义分析维度；空列表时由 DimensionGenerator 按主题动态生成 4-6 个",
    )
    use_rag: bool = Field(default=False, description="直答时是否启用历史报告 RAG 检索")
    attachment_ids: List[str] = Field(
        default_factory=list,
        description="用户上传的附件 ID 列表，会作为采集阶段的一手资料",
    )


class FollowUpRequest(BaseModel):
    message: str = Field(..., description="追问消息内容")
    conversation_history: List[dict] = Field(
        default_factory=list,
        description="之前的对话历史，每个元素包含 role 和 content",
    )
    use_rag: bool = Field(default=False, description="直答时是否启用历史报告 RAG 检索")
    attachment_ids: List[str] = Field(
        default_factory=list,
        description="用户上传的附件 ID 列表，会作为采集阶段的一手资料",
    )
    # 历史追问聚合 spec: 追问时指向父工作流的 workflow_id,用于在 DB 中建立父子关联
    parent_workflow_id: Optional[str] = Field(
        default=None,
        description="追问的父工作流 ID,None 表示本次请求应作为顶层对话",
    )


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

    # 修复:有附件(尤其是图片)时强制走 direct 路径,保证多模态 LLM 能看到附件
    if req.attachment_ids and decision.action == "orchestrate":
        logger.info(
            "Overriding 'orchestrate' to 'direct' in /start because %d attachment(s) present",
            len(req.attachment_ids),
        )
        decision = replace(decision, action="direct", intent_type="direct_with_attachment")

    if decision.action == "direct":
        state = await workflow_service.create_workflow(
            topic=req.topic,
            max_items=0,
            dimensions=[],
            use_rag=effective_use_rag,
            attachment_ids=req.attachment_ids,
            initial_stage="collecting",
        )
        state.is_direct_response = True
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "is_direct_response": True,
        })

    if decision.action == "reentry":
        # 校验 target_stage,失败回退到 collecting(防御 LLM 误判)
        target_stage = decision.target_stage if decision.target_stage in STAGE_SEQUENCE else "collecting"
        state = await workflow_service.create_workflow(
            topic=req.topic,
            max_items=req.max_items,
            dimensions=req.dimensions,
            use_rag=effective_use_rag,
            attachment_ids=req.attachment_ids,
            initial_stage=target_stage,
        )
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "intent_type": decision.intent_type,
            "target_stage": target_stage,
            "user_feedback": decision.user_feedback or "",
        })

    # decision.action == "orchestrate"（启动完整四阶段工作流）
    state = await workflow_service.create_workflow(
        topic=req.topic,
        max_items=req.max_items,
        dimensions=req.dimensions,
        use_rag=effective_use_rag,
        attachment_ids=req.attachment_ids,
        initial_stage="collecting",
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

    # 修复:追问时若携带了附件(尤其是图片),无论意图分类结果如何都走 direct 路径,
    # 否则 orchestrate 路径下附件会被 CollectorAgent 当作"用户资料"对待,
    # LLM 接收不到多模态图片,只能回答"我无法查看图片"。
    has_attachments = bool(req.attachment_ids)
    if has_attachments and decision.action == "orchestrate":
        logger.info(
            "Overriding 'orchestrate' to 'direct' because %d attachment(s) present "
            "and multimodal LLM call only works in direct path",
            len(req.attachment_ids),
        )
        decision = replace(decision, action="direct", intent_type="direct_with_attachment")

    if decision.action == "orchestrate":
        state = await workflow_service.create_workflow(
            topic=req.message,
            max_items=10,  # 追问需要补充新数据,比首次(20)略少但远多于 5
            dimensions=req.dimensions,  # 空 list → Orchestrator 走 DimensionGenerator 动态生成
            conversation_history=req.conversation_history,
            use_rag=effective_use_rag,
            attachment_ids=req.attachment_ids,
            initial_stage="collecting",
            parent_workflow_id=req.parent_workflow_id,
        )
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "intent_type": decision.intent_type,
        })

    if decision.action == "reentry":
        target_stage = decision.target_stage if decision.target_stage in STAGE_SEQUENCE else "collecting"
        state = await workflow_service.create_workflow(
            topic=req.message,
            max_items=10,  # reentry 同样需要足够数据支撑分析
            dimensions=[],
            conversation_history=req.conversation_history,
            use_rag=effective_use_rag,
            attachment_ids=req.attachment_ids,
            initial_stage=target_stage,
            parent_workflow_id=req.parent_workflow_id,
        )
        return success_response(data={
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "intent_type": decision.intent_type,
            "target_stage": target_stage,
            "user_feedback": decision.user_feedback or "",
        })

    # decision.action == "direct"（追问为常规问题，走直答流）
    state = await workflow_service.create_workflow(
        topic=req.message,
        max_items=0,
        dimensions=[],
        conversation_history=req.conversation_history,
        use_rag=effective_use_rag,
        attachment_ids=req.attachment_ids,
        initial_stage="collecting",
        parent_workflow_id=req.parent_workflow_id,
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
        workflow_service.run_pipeline_stream(state, use_rag=state.use_rag),
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


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="Workflow status: idle, running, completed, failed")


@router.patch("/{workflow_id}/status", response_model=ResponseModel)
async def update_workflow_status(
    workflow_id: str,
    req: UpdateStatusRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """更新 workflow 状态（用于前端 direct response 完成状态持久化）。"""
    valid_statuses = {"idle", "running", "completed", "failed"}
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}. Must be one of {valid_statuses}")

    state = await workflow_service.get_workflow(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    state.status = req.status
    await workflow_service._persist_stage_update(state)

    return success_response(data={"workflow_id": workflow_id, "status": req.status})


@router.get("/history/list", response_model=ResponseModel)
async def get_workflow_history(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    return success_response(data=await workflow_service.get_history())


@router.delete("/{workflow_id}", response_model=ResponseModel)
async def delete_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """删除指定工作流记录(内存 + DB)。"""
    success = await workflow_service.delete_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return success_response(data={"workflow_id": workflow_id})


@router.post("/{workflow_id}/stop", response_model=ResponseModel)
async def stop_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """停止正在运行的工作流（用户点击停止按钮）。"""
    success = await workflow_service.stop_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return success_response(data={"workflow_id": workflow_id})