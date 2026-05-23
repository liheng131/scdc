"""
事件规则 API 路由

提供事件监听规则的 CRUD 管理，支持以下事件类型：
- webhook: 接收外部 Webhook 推送后触发分析
- keyword: 文本内容包含指定关键词时触发
- metric: 指标值达到阈值时触发
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.schemas.event_rule import EventRuleCreate, EventRuleUpdate, EventRuleOut
from app.services.event_trigger import EventTriggerService

router = APIRouter()
event_service = EventTriggerService()

@router.post("/rules", response_model=ResponseModel)
async def create_event_rule(
    rule: EventRuleCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await event_service.create_rule(session, rule, current_user.id)
    return success_response(data=EventRuleOut.model_validate(obj).model_dump())

@router.get("/rules", response_model=ResponseModel)
async def list_event_rules(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    lst = await event_service.list_rules(session, current_user.id)
    return success_response(data=[EventRuleOut.model_validate(x).model_dump() for x in lst])

@router.put("/rules/{rule_id}", response_model=ResponseModel)
async def update_event_rule(
    rule_id: int,
    up: EventRuleUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await event_service.update_rule(session, rule_id, up)
    if not obj:
        raise HTTPException(status_code=404, detail="Rule not found")
    return success_response(data=EventRuleOut.model_validate(obj).model_dump())

@router.delete("/rules/{rule_id}", response_model=ResponseModel)
async def delete_event_rule(
    rule_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    ok = await event_service.delete_rule(session, rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    return success_response(msg="Rule deleted")

@router.post("/webhook", response_model=ResponseModel)
async def receive_webhook(
    payload: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_db)
) -> Any:
    res = await event_service.process_webhook(session, payload)
    return success_response(data=res)
