"""
通知规则 API 路由

提供通知渠道和触发条件的 CRUD 管理。

支持两种通知渠道：
- email: 通过 SMTP 发送邮件（使用 Jinja2 模板渲染 HTML 正文）
- webhook: 向目标 URL 发送 POST 请求（兼容钉钉/飞书机器人格式）
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.schemas.notification import NotificationRuleCreate, NotificationRuleUpdate, NotificationRuleOut
from app.services.notification import NotificationService

router = APIRouter()
notif_service = NotificationService()

@router.post("/rules", response_model=ResponseModel)
async def create_notification_rule(
    rule: NotificationRuleCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await notif_service.create_rule(session, rule)
    return success_response(data=NotificationRuleOut.model_validate(obj).model_dump())

@router.get("/rules", response_model=ResponseModel)
async def list_notification_rules(
    enabled_only: bool = False,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    lst = await notif_service.list_rules(session, enabled_only)
    return success_response(data=[NotificationRuleOut.model_validate(x).model_dump() for x in lst])

@router.put("/rules/{rule_id}", response_model=ResponseModel)
async def update_notification_rule(
    rule_id: int,
    up: NotificationRuleUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await notif_service.update_rule(session, rule_id, up)
    if not obj:
        raise HTTPException(status_code=404, detail="Rule not found")
    return success_response(data=NotificationRuleOut.model_validate(obj).model_dump())

@router.delete("/rules/{rule_id}", response_model=ResponseModel)
async def delete_notification_rule(
    rule_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    ok = await notif_service.delete_rule(session, rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    return success_response(msg="Rule deleted")

@router.post("/test", response_model=ResponseModel)
async def test_notify(
    trigger: str = Body(..., embed=True),
    title: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    res = await notif_service.notify(session, trigger, title, content)
    return success_response(data=res)
