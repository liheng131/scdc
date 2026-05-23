"""
大纲模板（Templates）API 路由

提供报告大纲模板的 CRUD 管理和模板渲染预览功能。

模板是结构化的 JSON 大纲定义，用于指导 ReporterAgent 生成符合规格的报告。
模板支持 scope（全局/个人）和 status（草稿/已发布）筛选。
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.schemas.template import TemplateCreate, TemplateUpdate, TemplateOut
from app.services.template import TemplateService

router = APIRouter()
tmpl_service = TemplateService()

@router.post("", response_model=ResponseModel)
async def create_template(
    tmpl: TemplateCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """创建新模板"""
    try:
        obj = await tmpl_service.create_template(session, tmpl)
        return success_response(data=TemplateOut.model_validate(obj).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=ResponseModel)
async def list_templates(
    scope: Optional[str] = None,     # 筛选范围：global / personal
    status: Optional[str] = None,    # 筛选状态：draft / published
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """获取模板列表，支持按范围和状态筛选"""
    lst = await tmpl_service.list_templates(session, scope=scope, status=status, skip=skip, limit=limit)
    return success_response(data=[TemplateOut.model_validate(x).model_dump() for x in lst])

@router.get("/{tmpl_id}", response_model=ResponseModel)
async def get_template(
    tmpl_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """获取单个模板详情"""
    obj = await tmpl_service.get_template(session, tmpl_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Template not found")
    return success_response(data=TemplateOut.model_validate(obj).model_dump())

@router.put("/{tmpl_id}", response_model=ResponseModel)
async def update_template(
    tmpl_id: int,
    up: TemplateUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """更新模板"""
    try:
        obj = await tmpl_service.update_template(session, tmpl_id, up)
        if not obj:
            raise HTTPException(status_code=404, detail="Template not found")
        return success_response(data=TemplateOut.model_validate(obj).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{tmpl_id}", response_model=ResponseModel)
async def delete_template(
    tmpl_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """删除模板"""
    ok = await tmpl_service.delete_template(session, tmpl_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")
    return success_response(msg="Template deleted")

@router.post("/{tmpl_id}/render", response_model=ResponseModel)
async def render_template_preview(
    tmpl_id: int,
    variables: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """
    模板渲染预览

    接受 JSON 变量字典，将模板中的占位符替换为实际值后返回渲染结果。
    用于在实际生成报告前预览模板效果。
    """
    try:
        res = await tmpl_service.render_template(session, tmpl_id, variables)
        return success_response(data=res)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
