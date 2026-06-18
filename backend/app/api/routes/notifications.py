"""
通知规则 API 路由

提供通知渠道和触发条件的 CRUD 管理。

支持两种通知渠道：
- email: 通过 SMTP 发送邮件（使用 Jinja2 模板渲染 HTML 正文）
- webhook: 向目标 URL 发送 POST 请求（兼容钉钉/飞书机器人格式）
"""

import asyncio
import logging
import os
import tempfile
import traceback as tb
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.models.report import Report
from app.schemas.notification import NotificationRuleCreate, NotificationRuleUpdate, NotificationRuleOut, ReportPushRequest
from app.services.notification import NotificationService
from app.services.report import ReportService

router = APIRouter()
notif_service = NotificationService()
rep_service = ReportService()

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

@router.post("/push", response_model=ResponseModel)
async def push_report(
    req: ReportPushRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """手动推送报告到指定邮箱"""
    stmt = select(Report).where(Report.id == req.report_id)
    res = await session.execute(stmt)
    report = res.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    title = f"【报告推送】{report.title}"
    summary = report.summary or (report.content_markdown[:500] if report.content_markdown else "无内容")
    html_content = f"<h2>{report.title}</h2><p>{summary}</p>"

    ok = await notif_service.send_direct("email", req.target_email, title, html_content)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send email")
    return success_response(msg="Report pushed successfully")


@router.post("/push-all", response_model=ResponseModel)
async def push_report_to_all_rules(
    req: ReportPushRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """推送报告到所有已启用的通知规则邮箱"""
    logger = logging.getLogger(__name__)
    try:
        logger.info("push-all start: report_id=%s, format=%s", req.report_id, req.format)
        stmt = select(Report).where(Report.id == req.report_id)
        res = await session.execute(stmt)
        report = res.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        logger.info("Report found: id=%s, title=%s", report.id, report.title)

        # 查找所有已启用的 email 类型通知规则
        from app.models.notification import NotificationRule
        rules_stmt = select(NotificationRule).where(
            NotificationRule.enabled == True,
            NotificationRule.channel == "email"
        )
        rules_res = await session.execute(rules_stmt)
        rules = rules_res.scalars().all()
        logger.info("Found %d enabled email rules", len(rules))

        if not rules:
            raise HTTPException(status_code=404, detail="No enabled email notification rules found")

        # 生成导出文件作为附件
        try:
            logger.info("Exporting report id=%s as %s", req.report_id, req.format)
            filename, media_type, content = await rep_service.export_report(session, req.report_id, req.format)
            logger.info("Export done: filename=%s, size=%d bytes", filename, len(content))
        except Exception as e:
            logger.error("Failed to export report for push: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to generate report attachment: {e}")

        # 保存临时文件
        with tempfile.NamedTemporaryFile(suffix=f'.{req.format}', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        logger.info("Temp file saved: %s", tmp_path)

        try:
            title = f"【报告推送】{report.title}"
            summary = report.summary or (report.content_markdown[:200] if report.content_markdown else "报告已推送，请查看附件。")
            html_content = f"<p>主题：{report.title}</p><p>{summary}</p><p>附件：{filename}</p>"

            # 向所有规则目标邮箱发送
            results = {}
            for rule in rules:
                logger.info("Sending to %s via rule %s", rule.target, rule.id)
                ok = await notif_service.send_direct("email", rule.target, title, html_content, attachments=[tmp_path])
                results[rule.target] = ok
                logger.info("Send result for %s: %s", rule.target, ok)

            failed = [email for email, ok in results.items() if not ok]
            if failed:
                logger.warning("Push failed for some emails: %s", failed)

            return success_response(
                msg=f"Report pushed to {len(rules)} email(s)",
                data={"total": len(rules), "results": results}
            )
        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                logger.info("Temp file cleaned: %s", tmp_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("push-all failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
