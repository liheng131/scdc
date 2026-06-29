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
from typing import List, Optional, Any, Dict
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
    chart_images: Optional[List[Dict[str, Any]]] = None
    dimension_illustrations: Optional[List[Dict[str, Any]]] = None
    # html-ppt Phase 1
    page_model: Optional[List[Dict[str, Any]]] = None
    theme: Optional[str] = None
    notes_summary: Optional[str] = None

@router.post("", response_model=ResponseModel)
@router.post("/", response_model=ResponseModel, include_in_schema=False)
async def create_report(
    rep: ReportCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """创建新报告

    同时注册 "" 与 "/" 两条路径 (main.py: redirect_slashes=False 避免丢 Authorization 头):
    - POST /api/v1/reports
    - POST /api/v1/reports/
    OpenAPI 文档仅显示前者 (include_in_schema=False), 实际两条都可用.
    """
    obj = await rep_service.create_report(session, rep)
    return success_response(data=ReportOut.model_validate(obj).model_dump())

@router.get("", response_model=ResponseModel)
@router.get("/", response_model=ResponseModel, include_in_schema=False)
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
        chart_images=req.chart_images,
        dimension_illustrations=req.dimension_illustrations,
        # html-ppt Phase 1
        page_model=req.page_model,
        theme=req.theme,
        notes_summary=req.notes_summary,
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
        # lazy 模式：用户在 UI 上传 = 用户主动确认，立即同步触发 Milvus 写入（暂时禁用，避免过慢）
        # await rep_service.upload_to_vector_store_if_pending(session, obj.id)
        # 重新读取以拿到更新后的 pending_vector_upload / vector_uploaded_at
        await session.refresh(obj)
        return success_response(data=ReportOut.model_validate(obj).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{report_id}/preview")
async def preview_report_html(
    report_id: int,
    theme: str = Query("minimal-white", description="html-ppt 主题名（36 套之一）"),
    current_user: User = Depends(get_current_active_user_sse),
    session: AsyncSession = Depends(get_db)
) -> Response:
    """
    预览报告的 html-ppt HTML 版本

    返回完整的 html-ppt 风格 HTML 页面，可直接嵌入 iframe 展示。
    与导出流程使用相同的 HTML 生成逻辑，确保所见即所得。

    Phase 1:
    - 优先使用 report.page_model（结构化 PageModel 列表）
    - 旧报告（page_model IS NULL）回退到 MarkdownPageParser 路径
    - theme 参数: 不在白名单时降级到 minimal-white + WARN 日志
    """
    from app.services.markdown_parser import MarkdownPageParser
    from app.services.quality_validator import QualityValidator
    from app.services.html_report_generator import HTMLReportGenerator, HTMLPageModel, HTMLTextBlock, HTMLImageBlock, LayoutType

    report = await rep_service.get_report(session, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 0) 最优先：直接使用存储的 html_content（由 ReporterAgent 生成，包含完整图表/KPI/布局）
    if report.html_content and len(report.html_content.strip()) > 500:
        # 替换主题（如果用户请求了不同主题）
        from app.services.html_report_generator import HTMLReportGenerator as _Gen
        available_themes = _Gen(theme="minimal-white").available_themes
        if theme not in available_themes:
            theme = "minimal-white"

        html_content = report.html_content
        import re
        # 替换 data-theme 属性
        html_content = re.sub(r'data-theme="[^"]*"', f'data-theme="{theme}"', html_content)
        # 替换主题 CSS 链接
        html_content = re.sub(
            r'href="[^"]*themes/[^"]*\.css"',
            f'href="/static/html-ppt/assets/themes/{theme}.css"',
            html_content,
        )
        # 修复所有 assets/ 相对路径 → 绝对路径（fonts.css/base.css/runtime.js 等）
        # 避免从 /api/v1/reports/{id}/preview 解析时变成 404
        html_content = html_content.replace(
            'href="assets/', 'href="/static/html-ppt/assets/'
        )
        html_content = html_content.replace(
            "href='assets/", "href='/static/html-ppt/assets/"
        )
        html_content = html_content.replace(
            'src="assets/', 'src="/static/html-ppt/assets/'
        )
        html_content = html_content.replace(
            "src='assets/", "src='/static/html-ppt/assets/"
        )
        # 修复 data-theme-base（runtime.js 动态加载主题用）
        html_content = html_content.replace(
            'data-theme-base="assets/', 'data-theme-base="/static/html-ppt/assets/'
        )

        # 确保所有幻灯片在预览模式下可见（iframe 中 runtime.js 可能未执行）
        # 1) 给 body 添加 single class（如果是预览模式，但 single class 还未添加）
        if 'class="single"' not in html_content and "<body " in html_content:
            html_content = html_content.replace("<body ", '<body class="single" ', 1)
        # 2) 确保 deck 允许滚动（overflow: auto; height: auto）
        if '<div class="deck"' in html_content and 'overflow:auto;height:auto' not in html_content:
            html_content = html_content.replace(
                '<div class="deck"', '<div class="deck" style="overflow:auto;height:auto"', 1
            )
        # 3) 注入 CSS 补丁 + fallback JS（body.single 模式：内容不截断 + 键盘滚动导航）
        SINGLE_CSS_PATCH = (
            '<style>body.single .deck{height:auto!important;overflow:auto!important} '
            'body.single .slide{min-height:100vh;height:auto;overflow:visible;justify-content:flex-start}</style>'
        )
        if SINGLE_CSS_PATCH not in html_content:
            html_content = html_content.replace('</head>', SINGLE_CSS_PATCH + '\n</head>', 1)
        FALLBACK_SCRIPT = (
            '<script>document.addEventListener("DOMContentLoaded",function(){'
            'var s=document.querySelectorAll(".slide");'
            'if(!s.length)return;'
            'if(!document.querySelector(".slide.is-active")){'
            's.forEach(function(el,i){'
            'el.style.opacity="1";el.style.pointerEvents="auto";el.style.transform="none";'
            'el.style.position="relative";el.style.height="auto";el.style.minHeight="100vh";el.style.overflow="visible";'
            'if(i===0)el.classList.add("is-active");'
            '});'
            '}'
            'var cur=0;'
            'function go(n){'
            'n=Math.max(0,Math.min(s.length-1,n));'
            'cur=n;'
            's.forEach(function(el,i){el.classList.toggle("is-active",i===n);});'
            's[n].scrollIntoView({behavior:"smooth",block:"start"});'
            'var b=document.querySelector(".progress-bar span");if(b)b.style.width=((n+1)/s.length*100)+"%";'
            '}'
            'document.addEventListener("keydown",function(e){'
            'if(e.metaKey||e.ctrlKey||e.altKey)return;'
            'switch(e.key){'
            'case "ArrowRight":case " ":case "PageDown":go(cur+1);e.preventDefault();break;'
            'case "ArrowLeft":case "PageUp":go(cur-1);e.preventDefault();break;'
            'case "Home":go(0);break;'
            'case "End":go(s.length-1);break;'
            '}});'
            '});</script>'
        )
        if FALLBACK_SCRIPT not in html_content and '</body>' in html_content:
            html_content = html_content.replace('</body>', FALLBACK_SCRIPT + '\n</body>')

        logging.getLogger(__name__).info(
            "[preview] report %s using stored html_content (%d chars, theme=%s)",
            report_id, len(html_content), theme,
        )
        return Response(
            content=html_content,
            media_type="text/html; charset=utf-8",
        )

    # 1) 主题白名单校验
    from app.services.html_report_generator import HTMLReportGenerator as _Gen
    available_themes = _Gen(theme="minimal-white").available_themes
    if theme not in available_themes:
        logging.getLogger(__name__).warning(
            "[preview] theme=%s not in whitelist, fallback to minimal-white", theme
        )
        theme = "minimal-white"

    # 2) 优先用 report.page_model, 旧报告 fallback 到 MarkdownPageParser
    page_model = None
    if report.page_model and isinstance(report.page_model, list) and len(report.page_model) > 0:
        try:
            # 从 JSON dict 列表重建 ReportPageModel
            from app.services.report_page_model import (
                ReportPageModel, PageModel, TextBlock, ImageBlock, TableBlock,
            )

            pages: List[PageModel] = []
            for idx, p in enumerate(report.page_model):
                tb = [
                    TextBlock(text=(b.get("text", "") or ""), style="body")
                    for b in (p.get("text_blocks") or [])
                ]
                # 分离 title / body
                title_text = p.get("title", "")
                if title_text:
                    tb = [TextBlock(text=title_text, style="title", font_size=22, bold=True)] + tb
                imgs = []
                for ib in (p.get("image_blocks") or []):
                    b64_or_url = ib.get("base64") or ib.get("url") or ""
                    if b64_or_url and not b64_or_url.startswith("data:"):
                        b64_or_url = f"data:image/png;base64,{b64_or_url}"
                    imgs.append(ImageBlock(
                        base64=b64_or_url.split(",", 1)[-1] if "," in b64_or_url else b64_or_url,
                        alt=ib.get("caption", "") or ib.get("alt", ""),
                    ))
                tables = []
                td = p.get("table_data")
                if td and isinstance(td, dict):
                    tables.append(TableBlock(
                        headers=td.get("headers", []) or [],
                        rows=td.get("rows", []) or [],
                    ))
                pages.append(PageModel(
                    page_type=p.get("page_type", "content") or "content",
                    title=title_text or f"第 {idx + 1} 页",
                    subtitle=p.get("subtitle", "") or "",
                    kicker=p.get("kicker", "") or "",
                    text_blocks=tb,
                    images=imgs,
                    tables=tables,
                    kpi_metrics=p.get("kpi_metrics", []) or [],
                    section_number=p.get("section_number", 0) or 0,
                    layout_hint="text_only",
                ))
            page_model = ReportPageModel(
                title=report.title,
                pages=pages,
                metadata={"task_id": report.task_id or str(report.id), "source": "page_model"},
            )
            logging.getLogger(__name__).info(
                "[preview] report %s using stored page_model: %d pages", report_id, len(pages)
            )
        except Exception as e:
            logging.getLogger(__name__).warning(
                "[preview] failed to rebuild page_model for report %s: %s, "
                "falling back to MarkdownPageParser", report_id, e,
            )
            page_model = None

    if page_model is None:
        # 旧报告兼容: 用 MarkdownPageParser 解析 content_markdown
        if not report.content_markdown:
            raise HTTPException(status_code=400, detail="Report has no content to preview")

        logging.getLogger(__name__).info(
            "[preview] report %s has no page_model, falling back to MarkdownPageParser",
            report_id,
        )
        parser = MarkdownPageParser()
        page_model = parser.parse(
            markdown=report.content_markdown,
            title=report.title,
            chart_images=report.images or [],
            metadata={"task_id": report.task_id or str(report.id), "source": "markdown"},
        )
        # 质量校验
        validator = QualityValidator()
        validation = validator.validate(page_model)
        page_model = validation.fixed_model or page_model

    # 3) 转换为 HTML 页面模型并生成 HTML（使用绝对路径确保从任何 URL 加载都能正确解析静态资源）
    html_pages = rep_service._convert_pages_to_html(page_model.pages)
    generator = HTMLReportGenerator(theme=theme, use_absolute_paths=True)
    html_content = generator.generate(html_pages)

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
    )


@router.get("/{report_id}/inline-html")
async def inline_html_report(
    report_id: int,
    theme: str = Query("minimal-white"),
    current_user: User = Depends(get_current_active_user_sse),
    session: AsyncSession = Depends(get_db)
) -> Response:
    """独立 HTML 文件（自包含 + 键盘导航可用）

    与 /preview 的区别：去掉 body.single（单页滚动模式），改为正常的
    position:absolute 堆叠模式，让 runtime.js 的键盘翻页正常工作。
    """
    import re
    from app.services.html_report_generator import HTMLReportGenerator as _Gen
    html_response = await preview_report_html(report_id, theme, current_user, session)
    html_content = html_response.body.decode("utf-8") if isinstance(html_response.body, bytes) else str(html_response.body)

    # ── 去掉 body.single，恢复正常的 absolute 堆叠模式 ──
    html_content = html_content.replace('class="single" ', '')
    html_content = html_content.replace('class="single"', '')
    html_content = html_content.replace("class='single' ", '')

    # ── 去掉 deck 的 overflow/height 覆盖（normal 模式需要默认值） ──
    html_content = re.sub(
        r'<div class="deck" style="overflow:auto;height:auto"',
        '<div class="deck"',
        html_content,
    )

    # ── 移除旧 fallback JS（强制所有 slide position:relative，破坏键盘导航）──
    html_content = re.sub(
        r'<script>document\.addEventListener\([\x27"]DOMContentLoaded[\x27"].*?style\.position\s*=\s*[\x27"]relative[\x27"].*?</script>',
        '',
        html_content,
        flags=re.DOTALL,
    )
    # ── 注入启动脚本：只激活 slide 0，不破坏 position:absolute 堆叠 ──
    INIT_SCRIPT = (
        '<script>document.addEventListener("DOMContentLoaded",function(){'
        'var slides=document.querySelectorAll(".slide");'
        'if(slides.length&&!document.querySelector(".slide.is-active")){'
        ' slides[0].classList.add("is-active");'
        ' var bar=document.querySelector(".progress-bar span");'
        ' if(bar)bar.style.width=(1/slides.length*100)+"%";'
        '}});</script>'
    )
    if '</body>' in html_content:
        html_content = html_content.replace('</body>', INIT_SCRIPT + '\n</body>')

    # ── 内联所有 CSS/JS ──
    inlined = _Gen.make_self_contained(html_content)
    return Response(content=inlined, media_type="text/html; charset=utf-8")


@router.get("/{report_id}/export")
async def export_report(
    report_id: int,
    fmt: str = Query("docx", description="导出格式:docx、pdf、md、pptx、html"),
    template_id: Optional[str] = Query(None, description="PPT 母版模板 ID（仅当 fmt=pptx 时生效）"),
    use_html_pipeline: bool = Query(True, description="是否使用HTML生成流程（高质量）"),
    theme: str = Query("minimal-white", description="html-ppt 主题名（36 套之一，仅 html/md/docx/pdf 生效）"),
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
        # 首次导出时自动写入 Milvus（暂时禁用，避免导出过慢）
        # await rep_service.upload_to_vector_store_if_pending(session, report_id)

        if use_html_pipeline:
            # 使用新的 HTML 生成流程
            # 布局决策由 ReportService._choose_layout 统一处理, 不再需要 ReporterAgent.

            # 读取报告
            report = await rep_service.get_report(session, report_id)
            if not report:
                raise ValueError("Report not found")

            # Phase 1: 优先用 report.page_model, 旧报告 fallback 到 MarkdownPageParser
            from app.services.markdown_parser import MarkdownPageParser
            from app.services.quality_validator import QualityValidator
            from app.services.report_page_model import (
                ReportPageModel, PageModel, TextBlock, ImageBlock, TableBlock,
            )

            page_model = None
            if report.page_model and isinstance(report.page_model, list) and len(report.page_model) > 0:
                try:
                    pages: List[PageModel] = []
                    for idx, p in enumerate(report.page_model):
                        # 注意: 不能用 tb 作为局部变量, 会遮蔽顶部的 `import traceback as tb`
                        tb_list = [
                            TextBlock(text=(b.get("text", "") or ""), style="body")
                            for b in (p.get("text_blocks") or [])
                        ]
                        title_text = p.get("title", "")
                        if title_text:
                            tb_list = [TextBlock(text=title_text, style="title", font_size=22, bold=True)] + tb_list
                        imgs = []
                        for ib in (p.get("image_blocks") or []):
                            b64_or_url = ib.get("base64") or ib.get("url") or ""
                            if b64_or_url and not b64_or_url.startswith("data:"):
                                b64_or_url = f"data:image/png;base64,{b64_or_url}"
                            imgs.append(ImageBlock(
                                base64=b64_or_url.split(",", 1)[-1] if "," in b64_or_url else b64_or_url,
                                alt=ib.get("caption", "") or ib.get("alt", ""),
                            ))
                        tables = []
                        td = p.get("table_data")
                        if td and isinstance(td, dict):
                            tables.append(TableBlock(
                                headers=td.get("headers", []) or [],
                                rows=td.get("rows", []) or [],
                            ))
                        pages.append(PageModel(
                            page_type=p.get("page_type", "content") or "content",
                            title=title_text or f"第 {idx + 1} 页",
                            subtitle=p.get("subtitle", "") or "",
                            kicker=p.get("kicker", "") or "",
                            text_blocks=tb_list,
                            images=imgs,
                            tables=tables,
                            kpi_metrics=p.get("kpi_metrics", []) or [],
                            section_number=p.get("section_number", 0) or 0,
                            layout_hint="text_only",
                        ))
                    page_model = ReportPageModel(
                        title=report.title,
                        pages=pages,
                        metadata={"task_id": report.task_id or str(report.id), "source": "page_model"},
                    )
                    logging.getLogger(__name__).info(
                        "[export] report %s using stored page_model: %d pages", report_id, len(pages)
                    )
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        "[export] failed to rebuild page_model for report %s: %s, "
                        "falling back to MarkdownPageParser", report_id, e,
                    )
                    page_model = None

            if page_model is None:
                # 旧报告兼容: 走 MarkdownPageParser
                if not report.content_markdown:
                    filename, media_type, content = await rep_service.export_report(
                        session, report_id, fmt, template_id=template_id,
                    )
                else:
                    parser = MarkdownPageParser()
                    page_model = parser.parse(
                        markdown=report.content_markdown,
                        title=report.title,
                        chart_images=report.images or [],
                        metadata={"task_id": report.task_id or str(report.id), "source": "markdown"},
                    )
                    validator = QualityValidator()
                    validation = validator.validate(page_model)
                    page_model = validation.fixed_model or page_model

            # 使用 HTML 流程导出
            filename, media_type, content = await rep_service.export_report_with_html_pipeline(
                session, report_id, fmt, page_model, template_id, theme=theme
            )
        else:
            # 使用旧版流程
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
        logging.getLogger(__name__).exception(
            "export_report failed (id=%s fmt=%s)", report_id, fmt,
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
