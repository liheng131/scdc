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

import asyncio
import base64
import io
import logging
import os
import re
import tempfile
from typing import Dict, List, Optional, Tuple
import docx
import docx.shared
from pptx import Presentation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.report import Report
from app.schemas.report import ReportCreate, ReportUpdate, ReportStatisticsItem
from app.services.embedding import EmbeddingService
from app.services.vectorstore import VectorStoreService

logger = logging.getLogger(__name__)

class ReportService:
    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    async def _embed_and_store(self, report_id: int, content_markdown: str):
        try:
            chunks = self._chunk_text(content_markdown)
            if not chunks:
                return
            emb_service = EmbeddingService()
            vectors = await emb_service.embed_texts_or_empty(chunks)
            if not vectors:
                logger.warning("Embedding returned empty, skipping vector store for report %d", report_id)
                return
            vs_service = VectorStoreService()
            if not vs_service._connected:
                logger.warning("Milvus not connected, skipping embedding for report %d", report_id)
                return
            vs_service.init_collection(len(vectors[0]))
            vs_service.insert(str(report_id), chunks, vectors)
            logger.info("Embedded %d chunks for report %d", len(chunks), report_id)
        except Exception as e:
            logger.warning("Failed to embed report %d: %s", report_id, e)

    async def create_report(self, session: AsyncSession, report_in: ReportCreate) -> Report:
        r = Report(
            task_id=report_in.task_id,
            title=report_in.title,
            version=report_in.version,
            status=report_in.status,
            summary=report_in.summary,
            content_markdown=report_in.content_markdown,
            storage_ref=report_in.storage_ref,
            images=report_in.chart_images if report_in.chart_images else [],  # NEW: persist chart_images
        )
        session.add(r)
        await session.commit()
        await session.refresh(r)
        if r.content_markdown:
            asyncio.create_task(self._embed_and_store(r.id, r.content_markdown))
        return r

    async def get_report(self, session: AsyncSession, report_id: int) -> Optional[Report]:
        stmt = select(Report).where(Report.id == report_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_reports(
        self, session: AsyncSession, task_id: Optional[str] = None, q: Optional[str] = None, skip: int = 0, limit: int = 20
    ) -> Tuple[List[Report], int]:
        """获取报告列表（分页），并返回符合条件的总记录数。

        返回:
            (报告列表, 总数)
        """
        base_stmt = select(Report)
        if task_id is not None:
            base_stmt = base_stmt.where(Report.task_id == task_id)
        if q:
            base_stmt = base_stmt.where(or_(Report.title.ilike(f"%{q}%"), Report.summary.ilike(f"%{q}%")))

        # 统计总数（应用相同的过滤条件）
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_res = await session.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        # 按创建时间倒序、ID 倒序排序，确保最新报告优先且顺序稳定
        stmt = base_stmt.order_by(Report.created_at.desc(), Report.id.desc()).offset(skip).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all()), total

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
        try:
            vs_service = VectorStoreService()
            vs_service.delete_by_report(str(report_id))
        except Exception as e:
            logger.warning("Failed to delete vectors for report %d: %s", report_id, e)
        await session.delete(r)
        await session.commit()
        return True

    async def create_from_workflow(
        self,
        session: AsyncSession,
        task_id: str,
        title: str,
        content_markdown: Optional[str] = None,
        summary: Optional[str] = None,
        chart_images: Optional[List[Dict[str, str]]] = None,  # NEW parameter
    ) -> Report:
        report_in = ReportCreate(
            task_id=task_id,
            title=title,
            status="published",
            content_markdown=content_markdown,
            summary=summary or (content_markdown[:200] if content_markdown else None),
            chart_images=chart_images,  # NEW: pass chart_images
        )
        return await self.create_report(session, report_in)

    async def upload_report(
        self,
        session: AsyncSession,
        file_content: bytes,
        filename: str,
        title: Optional[str] = None,
    ) -> Report:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

        if ext == "pdf":
            from app.parsers.pdf import PDFParser
            parser = PDFParser()
            result = await parser.parse(io.BytesIO(file_content), filename)
            content = result.content
        elif ext == "docx":
            from app.parsers.docx import DocxParser
            parser = DocxParser()
            result = await parser.parse(io.BytesIO(file_content), filename)
            content = result.content
        elif ext in ("md", "txt"):
            content = file_content.decode("utf-8", errors="replace")
        else:
            raise ValueError(f"Unsupported file type: .{ext}")

        report_in = ReportCreate(
            title=title or filename,
            status="published",
            content_markdown=content,
            summary=content[:200] if content else None,
        )
        return await self.create_report(session, report_in)

    async def get_statistics(
        self,
        session: AsyncSession,
        period: str,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 12
    ) -> List[ReportStatisticsItem]:
        """
        获取报告统计数据，按指定时间周期分组统计报告数量

        参数:
            session: 数据库会话
            period: 时间周期 ('day' | 'week' | 'month' | 'year'
            report_type: 预留参数，暂未使用
            status: 预留参数，暂未使用
            limit: 返回最近多少个时间周期

        返回:
            List[ReportStatisticsItem]: 包含标签和数量的统计列表，按时间正序排列
        """
        import datetime
        
        period_map = {
            'day': 'day',
            'week': 'week',
            'month': 'month',
            'year': 'year'
        }
        
        truncated_date = func.date_trunc(period_map[period], Report.created_at).label('period_date')
        
        stmt = (
            select(truncated_date, func.count(Report.id).label('count'))
            .group_by(truncated_date)
            .order_by(truncated_date.desc())
            .limit(limit)
        )
        
        res = await session.execute(stmt)
        results = res.all()
        
        # Build a dict of actual data: label -> count
        actual_data = {}
        for row in results:
            date_obj = row.period_date
            if period == 'day':
                label = date_obj.strftime('%Y-%m-%d')
            elif period == 'week':
                year = date_obj.year
                week = date_obj.isocalendar()[1]
                label = f'{year}-W{week:02d}'
            elif period == 'month':
                label = date_obj.strftime('%Y-%m')
            elif period == 'year':
                label = date_obj.strftime('%Y')
            else:
                label = date_obj.strftime('%Y-%m-%d')
            actual_data[label] = row.count
        
        # Generate complete period labels from now going back 'limit' periods
        now = datetime.datetime.now()
        all_labels = []
        
        for i in range(limit):
            if period == 'day':
                target = now - datetime.timedelta(days=i)
                label = target.strftime('%Y-%m-%d')
            elif period == 'week':
                target = now - datetime.timedelta(weeks=i)
                year = target.year
                week = target.isocalendar()[1]
                label = f'{year}-W{week:02d}'
            elif period == 'month':
                # Calculate month by subtracting i months from now
                month = now.month - i
                year = now.year
                while month <= 0:
                    month += 12
                    year -= 1
                label = f'{year}-{month:02d}'
            elif period == 'year':
                label = str(now.year - i)
            else:
                target = now - datetime.timedelta(days=i)
                label = target.strftime('%Y-%m-%d')
            
            all_labels.append(label)
        
        # Merge: use actual data if available, otherwise 0
        formatted_results = []
        for label in reversed(all_labels):
            count = actual_data.get(label, 0)
            formatted_results.append(ReportStatisticsItem(label=label, count=count))
        
        return formatted_results

    def generate_docx(self, report: Report, chart_images: List[Dict[str, str]] = None) -> bytes:
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
        if chart_images:
            doc.add_heading("数据可视化图表", 1)
            for ci in chart_images:
                doc.add_heading(ci.get("title", "图表"), 2)
                img_data = io.BytesIO(base64.b64decode(ci["base64"]))
                doc.add_picture(img_data, width=docx.shared.Inches(5))
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf.getvalue()

    def generate_pptx(self, report: Report, chart_images: List[Dict[str, str]] = None) -> bytes:
        prs = Presentation()
        title_slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_slide_layout)
        slide.shapes.title.text = report.title
        if len(slide.placeholders) > 1:
            slide.placeholders[1].text = report.summary or ""

        content = report.content_markdown or ""
        sections = re.split(r"\n(?=## )", content)
        content_slide_layout = prs.slide_layouts[1]

        for section in sections:
            section = section.strip()
            if not section:
                continue
            lines = section.split("\n")
            heading = lines[0].strip()
            if heading.startswith("## "):
                heading = heading[3:]

            slide = prs.slides.add_slide(content_slide_layout)
            slide.shapes.title.text = heading
            body = slide.placeholders[1]
            tf = body.text_frame
            tf.clear()

            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                p = tf.add_paragraph()
                p.text = line

        if chart_images:
            blank_layout = prs.slide_layouts[6]
            for ci in chart_images:
                slide = prs.slides.add_slide(blank_layout)
                img_data = io.BytesIO(base64.b64decode(ci["base64"]))
                slide.shapes.add_picture(img_data, docx.shared.Inches(1), docx.shared.Inches(1.5),
                                         width=docx.shared.Inches(8))

        buf = io.BytesIO()
        prs.save(buf)
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

    def generate_pdf(self, report: Report, chart_images: List[Dict[str, str]] = None) -> bytes:
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

        if chart_images:
            story.append(Paragraph("数据可视化图表", h1_style))
            for ci in chart_images:
                story.append(Paragraph(ci.get("title", "图表"), h2_style))
                img_data = io.BytesIO(base64.b64decode(ci["base64"]))
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    tmp.write(img_data.getvalue())
                    tmp.flush()
                    tmp_path = tmp.name
                try:
                    story.append(RLImage(tmp_path, width=400, height=250))
                    story.append(Spacer(1, 10))
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

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

        chart_images = r.images if isinstance(r.images, list) else []

        fmt = fmt.lower()
        if fmt == "docx":
            data = self.generate_docx(r, chart_images=chart_images)
            result = (f"report_{r.id}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", data)
        elif fmt == "pdf":
            data = self.generate_pdf(r, chart_images=chart_images)
            result = (f"report_{r.id}.pdf", "application/pdf", data)
        elif fmt == "pptx":
            data = self.generate_pptx(r, chart_images=chart_images)
            result = (f"report_{r.id}.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", data)
        elif fmt == "md" or fmt == "markdown":
            result = (f"report_{r.id}.md", "text/markdown", self.generate_markdown(r))
        else:
            raise ValueError("Unsupported format. Use docx, pdf, pptx, or md.")

        if r.content_markdown:
            asyncio.create_task(self._embed_and_store(r.id, r.content_markdown))

        return result
