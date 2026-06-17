"""
智能研报（Reports）API 路由

提供报告的 CRUD、列表筛选（按 task_id / 关键词）、多格式导出（docx/pdf/md/pptx）。

导出功能直接返回文件流，浏览器自动触发下载。
导出成功后自动触发邮件推送（向 notification_rules 中 trigger=report_ready 且 enabled=true 的邮箱发送）。
"""

import asyncio
import logging
import os
import tempfile
import traceback as tb
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_current_active_user_sse, get_db
from app.api.responses import success_response, ResponseModel
from app.core.db import async_session_factory
from app.models.user import User
from app.models.report import Report
from app.schemas.report import ReportCreate, ReportUpdate, ReportOut, ReportStatisticsResponse
from app.schemas.notification import ReportPushRequest
from app.services.report import ReportService
from app.services.notification import NotificationService

router = APIRouter()
rep_service = ReportService()


class CreateFromWorkflowRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    title: str = Field(..., max_length=255)
    content_markdown: Optional[str] = None
    summary: Optional[str] = None

@router.post("/", response_model=ResponseModel)
async def create_report(
    rep: ReportCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """创建新报告"""
    obj = await rep_service.create_report(session, rep)
    return success_response(data=ReportOut.model_validate(obj).model_dump())

@router.get("/", response_model=ResponseModel)
async def list_reports(
    task_id: Optional[str] = None,    # 按任务 ID 筛选
    q: Optional[str] = None,           # 关键词搜索（匹配标题和摘要）
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """获取报告列表，支持按任务 ID 和关键词筛选"""
    items, total = await rep_service.list_reports(session, task_id=task_id, q=q, skip=skip, limit=limit)
    return success_response(data={
        "items": [ReportOut.model_validate(x).model_dump() for x in items],
        "total": total,
    })

@router.get("/statistics", response_model=ResponseModel[ReportStatisticsResponse])
async def get_report_statistics(
    period: str = Query(...),
    report_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(12, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """
    获取报告统计数据，按指定时间周期分组统计报告数量
    
    参数:
        period: 时间周期，仅支持 'day' | 'week' | 'month' | 'year'
        report_type: 报告类型，预留参数，暂未使用
        status: 报告状态，预留参数，暂未使用
        limit: 返回最近多少个时间周期的数据，默认 12，范围 1-100
        current_user: 当前登录用户
        session: 数据库会话
    
    返回:
        ReportStatisticsResponse: 包含时间周期和统计项的响应
    """
    if period not in ['day', 'week', 'month', 'year']:
        raise HTTPException(status_code=422, detail="Invalid period. Allowed values: day, week, month, year")
    
    items = await rep_service.get_statistics(
        session, period=period, report_type=report_type, status=status, limit=limit
    )
    return success_response(data=ReportStatisticsResponse(period=period, items=items))

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

@router.post("/create-from-workflow", response_model=ResponseModel)
async def create_report_from_workflow(
    req: CreateFromWorkflowRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    obj = await rep_service.create_from_workflow(
        session,
        task_id=req.task_id,
        title=req.title,
        content_markdown=req.content_markdown,
        summary=req.summary,
    )
    return success_response(data=ReportOut.model_validate(obj).model_dump())

@router.post("/upload", response_model=ResponseModel)
async def upload_report(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    try:
        content = await file.read()
        obj = await rep_service.upload_report(session, content, file.filename, title)
        # lazy 模式：用户在 UI 上传 = 用户主动确认，立即同步触发 Milvus 写入
        await rep_service.upload_to_vector_store_if_pending(session, obj.id)
        # 重新读取以拿到更新后的 pending_vector_upload / vector_uploaded_at
        await session.refresh(obj)
        return success_response(data=ReportOut.model_validate(obj).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{report_id}/export")
async def export_report(
    report_id: int,
    fmt: str = Query("docx", description="导出格式:docx、pdf 或 md"),
    template_id: Optional[str] = Query(None, description="PPT 母版模板 ID（仅当 fmt=pptx 时生效）"),
    current_user: User = Depends(get_current_active_user_sse),
    session: AsyncSession = Depends(get_db)
) -> Response:
    """
    导出报告为指定格式的文件

    不返回 JSON,而是直接返回文件流(Response),
    通过 Content-Disposition 头触发浏览器下载。

    lazy 行为:首次导出时(pending_vector_upload=True)自动同步触发 Milvus 写入,
    这样"用户导出"作为用户主动确认的信号,触发 RAG 入库。

    导出成功后自动触发邮件推送（向 notification_rules 中 trigger=report_ready 且 enabled=true 的邮箱发送）。

    错误处理:
    - 报告不存在 / 参数错误 → 400
    - 文件生成过程中 reportlab/docx/pptx 抛异常 → 500,并把异常信息回显到 detail
      (这样前端 fetch 失败时能看到真实原因,便于排查 CJK 字体等问题)
    """
    try:
        # 首次导出时自动写入 Milvus
        await rep_service.upload_to_vector_store_if_pending(session, report_id)
        filename, media_type, content = await rep_service.export_report(
            session, report_id, fmt, template_id=template_id,
        )

        # 导出成功后异步触发邮件推送
        asyncio.create_task(_trigger_export_notification(report_id, filename, content))

        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.getLogger(__name__).error(
            "export_report failed (id=%s fmt=%s): %s\n%s",
            report_id, fmt, e, tb.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"生成 {fmt.upper()} 报告失败: {type(e).__name__}: {e}",
        )


async def _trigger_export_notification(report_id: int, filename: str, content: bytes) -> None:
    """导出成功后异步触发邮件推送"""
    try:
        # 保存临时文件
        suffix = filename.rsplit('.', 1)[-1] if '.' in filename else 'md'
        with tempfile.NamedTemporaryFile(suffix=f'.{suffix}', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            async with async_session_factory() as sess:
                # 读取报告信息
                result = await sess.execute(sa_select(Report).where(Report.id == report_id))
                report = result.scalar_one_or_none()
                if not report:
                    return

                notif_svc = NotificationService()
                title = f"【报告导出】{report.title}"
                summary = report.summary or (report.content_markdown[:200] if report.content_markdown else "报告已导出，请查看附件。")
                html_content = f"<p>主题：{report.title}</p><p>{summary}</p><p>附件：{filename}</p>"

                await notif_svc.notify(
                    session=sess,
                    trigger="report_ready",
                    title=title,
                    content=html_content,
                    attachments=[tmp_path],
                )
                logging.getLogger(__name__).info("Export notification sent for report %s", report_id)
        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to send export notification (report_id=%s): %s", report_id, e)
