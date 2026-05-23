"""
报告服务

负责报告的 CRUD 及多格式导出（Markdown → DOCX/PDF）。

导出功能说明：
- generate_docx(): 使用 python-docx 生成 Word 文档，按 Markdown 标题层级映射样式
- generate_pdf(): 使用 reportlab 生成 PDF，标题自动映射到对应字体样式
- generate_markdown(): 直接拼接 Markdown 内容返回原始文本
- export_report(): 统一入口，根据 fmt 参数路由到对应生成器

为什么同时支持 DOCX 和 PDF：
- DOCX 面向编辑（用户下载后可在 Word 中继续修改）
- PDF 面向分发（格式固定，跨设备查看体验一致）
- Markdown 面向集成（可直接导入 Notion、Obsidian 等知识管理工具）
"""

import io
from typing import List, Optional, Tuple
import docx
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.report import Report
from app.schemas.report import ReportCreate, ReportUpdate

class ReportService:
    async def create_report(self, session: AsyncSession, report_in: ReportCreate) -> Report:
        r = Report(
            task_id=report_in.task_id,
            title=report_in.title,
            version=report_in.version,
            status=report_in.status,
            summary=report_in.summary,
            content_markdown=report_in.content_markdown,
            storage_ref=report_in.storage_ref
        )
        session.add(r)
        await session.commit()
        await session.refresh(r)
        return r

    async def get_report(self, session: AsyncSession, report_id: int) -> Optional[Report]:
        stmt = select(Report).where(Report.id == report_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_reports(
        self, session: AsyncSession, task_id: Optional[int] = None, q: Optional[str] = None, skip: int = 0, limit: int = 20
    ) -> List[Report]:
        stmt = select(Report).order_by(Report.id.desc())
        if task_id:
            stmt = stmt.where(Report.task_id == task_id)
        if q:
            stmt = stmt.where(or_(Report.title.ilike(f"%{q}%"), Report.summary.ilike(f"%{q}%")))
        stmt = stmt.offset(skip).limit(limit)
        res = await session.execute(stmt)
        return res.scalars().all()

    async def update_report(self, session: AsyncSession, report_id: int, up: ReportUpdate) -> Optional[Report]:
        r = await self.get_report(session, report_id)
        if not r:
            return None
        data = up.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(r, k, v)
        await session.commit()
        await session.refresh(r)
        return r

    async def delete_report(self, session: AsyncSession, report_id: int) -> bool:
        r = await self.get_report(session, report_id)
        if not r:
            return False
        await session.delete(r)
        await session.commit()
        return True

    def generate_docx(self, report: Report) -> bytes:
        """从 Markdown 报告生成 DOCX 文件，标题层级自动映射为 Word 样式"""
        doc = docx.Document()
        doc.add_heading(report.title, 0)
        doc.add_heading("执行摘要", 1)
        doc.add_paragraph(report.summary or "无摘要")
        doc.add_heading("详细内容", 1)
        for line in (report.content_markdown or "").split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("# "):
                doc.add_heading(line[2:], 1)
            elif line.startswith("## "):
                doc.add_heading(line[3:], 2)
            elif line.startswith("### "):
                doc.add_heading(line[4:], 3)
            else:
                doc.add_paragraph(line)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf.getvalue()

    def _get_cjk_stylesheet(self):
        """
        获取支持中文的 reportlab 样式表

        为什么需要自定义样式表：
        - reportlab 默认 getSampleStyleSheet() 使用 Helvetica 字体，不含中文字形
        - PDF 绘制中文时发现字体缺少对应 glyph，导致乱码
        - 需要注册中文字体并替换所有样式的 fontName

        字体选择：
        - 文泉驿微米黑 (WenQuanYi Micro Hei)：Linux 常用免费中文字体，包体小
        - Docker 中通过 apt-get install fonts-wqy-microhei 安装
        """
        font_paths = [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Docker Linux 路径
        ]
        cjk_font_name = None
        for path in font_paths:
            try:
                pdfmetrics.registerFont(TTFont('WQYMicroHei', path))
                cjk_font_name = 'WQYMicroHei'
                break
            except Exception:
                continue

        styles = getSampleStyleSheet()

        if cjk_font_name:
            for style_name in ['Title', 'Heading1', 'Heading2', 'Heading3', 'BodyText']:
                style = styles[style_name]
                style.fontName = cjk_font_name
                style.encoding = 'UTF-8'
        else:
            import logging
            logging.getLogger(__name__).warning("No CJK font found, PDF may display garbled Chinese text")

        return styles

    def generate_pdf(self, report: Report) -> bytes:
        """从 Markdown 报告生成 PDF 文件，支持中文字体"""
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        styles = self._get_cjk_stylesheet()
        t_style = styles['Title']
        h1_style = styles['Heading1']
        h2_style = styles['Heading2']
        body_style = styles['BodyText']

        story = [Paragraph(report.title, t_style), Spacer(1, 20)]
        story.append(Paragraph("执行摘要", h1_style))
        story.append(Paragraph(report.summary or "无", body_style))
        story.append(Spacer(1, 15))

        story.append(Paragraph("详细内容", h1_style))
        for line in (report.content_markdown or "").split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("# "):
                story.append(Spacer(1, 10))
                story.append(Paragraph(line[2:], h1_style))
            elif line.startswith("## "):
                story.append(Spacer(1, 8))
                story.append(Paragraph(line[3:], h2_style))
            else:
                story.append(Paragraph(line, body_style))
                story.append(Spacer(1, 4))

        doc.build(story)
        buf.seek(0)
        return buf.getvalue()

    def generate_markdown(self, report: Report) -> bytes:
        """直接返回 Markdown 原始内容，供下载"""
        content = f"# {report.title}\n\n## 执行摘要\n{report.summary or '无'}\n\n## 详细内容\n{report.content_markdown or ''}"
        return content.encode("utf-8")

    async def export_report(self, session: AsyncSession, report_id: int, fmt: str) -> Tuple[str, str, bytes]:
        """
        统一导出入口

        返回三元组：(文件名, MIME类型, 文件二进制内容)
        路由函数据此设置 HTTP 响应头（Content-Disposition + Content-Type）
        """
        r = await self.get_report(session, report_id)
        if not r:
            raise ValueError("Report not found")

        fmt = fmt.lower()
        if fmt == "docx":
            return f"report_{r.id}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", self.generate_docx(r)
        elif fmt == "pdf":
            return f"report_{r.id}.pdf", "application/pdf", self.generate_pdf(r)
        elif fmt == "md" or fmt == "markdown":
            return f"report_{r.id}.md", "text/markdown", self.generate_markdown(r)
        else:
            raise ValueError("Unsupported format. Use docx, pdf, or md.")
