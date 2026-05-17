from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.schemas.report import ReportCreate, ReportUpdate, ReportOut
from app.services.report import ReportService

router = APIRouter()
rep_service = ReportService()

@router.post("", response_model=ResponseModel)
async def create_report(
    rep: ReportCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await rep_service.create_report(session, rep)
    return success_response(data=ReportOut.model_validate(obj).model_dump())

@router.get("", response_model=ResponseModel)
async def list_reports(
    task_id: Optional[int] = None,
    q: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    lst = await rep_service.list_reports(session, task_id=task_id, q=q, skip=skip, limit=limit)
    return success_response(data=[ReportOut.model_validate(x).model_dump() for x in lst])

@router.get("/{report_id}", response_model=ResponseModel)
async def get_report(
    report_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await rep_service.get_report(session, report_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Report not found")
    return success_response(data=ReportOut.model_validate(obj).model_dump())

@router.put("/{report_id}", response_model=ResponseModel)
async def update_report(
    report_id: int,
    up: ReportUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await rep_service.update_report(session, report_id, up)
    if not obj:
        raise HTTPException(status_code=404, detail="Report not found")
    return success_response(data=ReportOut.model_validate(obj).model_dump())

@router.delete("/{report_id}", response_model=ResponseModel)
async def delete_report(
    report_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    ok = await rep_service.delete_report(session, report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Report not found")
    return success_response(msg="Report deleted")

@router.get("/{report_id}/export")
async def export_report(
    report_id: int,
    fmt: str = Query("docx", description="docx, pdf, 或 md"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Response:
    try:
        filename, media_type, content = await rep_service.export_report(session, report_id, fmt)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
