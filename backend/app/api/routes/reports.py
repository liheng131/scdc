"""
智能研报（Reports）API 路由

提供报告的 CRUD、列表筛选（按 task_id / 关键词）、多格式导出（docx/pdf/md）。

导出功能直接返回文件流，浏览器自动触发下载。
"""

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
    """创建新报告"""
    obj = await rep_service.create_report(session, rep)
    return success_response(data=ReportOut.model_validate(obj).model_dump())

@router.get("", response_model=ResponseModel)
async def list_reports(
    task_id: Optional[int] = None,    # 按任务 ID 筛选
    q: Optional[str] = None,           # 关键词搜索（匹配标题和摘要）
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """获取报告列表，支持按任务 ID 和关键词筛选"""
    lst = await rep_service.list_reports(session, task_id=task_id, q=q, skip=skip, limit=limit)
    return success_response(data=[ReportOut.model_validate(x).model_dump() for x in lst])

@router.get("/{report_id}", response_model=ResponseModel)
async def get_report(
    report_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """获取单个报告详情"""
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
    """更新报告信息"""
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
    """删除报告"""
    ok = await rep_service.delete_report(session, report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Report not found")
    return success_response(msg="Report deleted")

@router.get("/{report_id}/export")
async def export_report(
    report_id: int,
    fmt: str = Query("docx", description="导出格式：docx、pdf 或 md"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Response:
    """
    导出报告为指定格式的文件

    不返回 JSON，而是直接返回文件流（Response），
    通过 Content-Disposition 头触发浏览器下载。
    """
    try:
        filename, media_type, content = await rep_service.export_report(session, report_id, fmt)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
