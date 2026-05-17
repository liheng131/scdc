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
    try:
        obj = await tmpl_service.create_template(session, tmpl)
        return success_response(data=TemplateOut.model_validate(obj).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=ResponseModel)
async def list_templates(
    scope: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    lst = await tmpl_service.list_templates(session, scope=scope, status=status, skip=skip, limit=limit)
    return success_response(data=[TemplateOut.model_validate(x).model_dump() for x in lst])

@router.get("/{tmpl_id}", response_model=ResponseModel)
async def get_template(
    tmpl_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
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
    try:
        res = await tmpl_service.render_template(session, tmpl_id, variables)
        return success_response(data=res)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
