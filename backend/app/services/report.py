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
from typing import Any, Dict, List, Optional, Tuple
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
from app.services.ppt_template import PPTTemplateService
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
        """DEPRECATED: 旧版自动嵌入入口，由 export_report 触发。

        自"lazy 向量库写入"改造后，写入时机已统一迁移到
        `VectorstoreUploadService.upload_report()`，并由 export / upload 端点
        在用户主动确认时触发。本方法保留仅为向后兼容，新逻辑请走
        `upload_to_vector_store_if_pending()`。
        """
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
            pending_vector_upload=True,  # NEW: lazy 模式默认待写入
        )
        session.add(r)
        await session.commit()
        await session.refresh(r)
        # 注意：lazy 模式下不在此处触发 Milvus 写入
        return r

    async def upload_to_vector_store_if_pending(self, session: AsyncSession, report_id: int) -> bool:
        """如果报告 pending_vector_upload=True，则嵌入 Milvus 并更新状态。

        触发时机：用户首次导出报告（PDF/DOCX/PPTX/MD 任一格式）或用户上传报告。
        写入成功后将 pending_vector_upload 标记为 False 并记录上传时间。

        Returns:
            True 表示本次确实写入了 Milvus，False 表示已写入过或写入失败。
        """
        from app.services.vectorstore_upload import vs_upload_service
        import datetime

        r = await self.get_report(session, report_id)
        if not r:
            return False
        if not r.pending_vector_upload:
            return False
        chunks = await vs_upload_service.upload_report(r)
        if chunks > 0:
            r.pending_vector_upload = False
            r.vector_uploaded_at = datetime.datetime.utcnow().isoformat()
            await session.commit()
            await session.refresh(r)
            return True
        return False

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
        chart_images: Optional[List[Dict[str, str]]] = None,
        dimension_illustrations: Optional[List[Dict[str, Any]]] = None,
    ) -> Report:
        # 合并 chart_images 和 dimension_illustrations
        all_images = []
        if chart_images:
            all_images.extend(chart_images)
        if dimension_illustrations:
            # dimension_illustrations 格式: [{"section": str, "title": str, "base64": str, "position": int}]
            # 转换为 chart_images 格式并保留 section 和 position 信息
            for ill in dimension_illustrations:
                all_images.append({
                    "title": ill.get("title", ""),
                    "base64": ill.get("base64", ""),
                    "section": ill.get("section", ""),
                    "position": ill.get("position", 0),
                })

        report_in = ReportCreate(
            task_id=task_id,
            title=title,
            status="published",
            content_markdown=content_markdown,
            summary=summary or (content_markdown[:200] if content_markdown else None),
            chart_images=all_images,
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

    # ------------------------------------------------------------------
    # 配图匹配辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_section_chart_map(chart_images: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
        """将 chart_images 按 section 字段分组，返回 {section_name: [chart, ...]}。

        没有 section 字段的配图会被忽略（由调用方走旧逻辑兜底）。
        """
        mapping: Dict[str, List[Dict[str, str]]] = {}
        if not chart_images:
            return mapping
        for ci in chart_images:
            section = (ci.get("section") or "").strip()
            if not section:
                continue
            mapping.setdefault(section, []).append(ci)
        return mapping

    @staticmethod
    def _match_section(heading: str, section_name: str) -> bool:
        """判断 Markdown 章节标题是否与配图的 section 字段匹配。

        匹配规则：
        1. 完全相等（忽略首尾空白）
        2. 章节标题包含 section 名称（子串匹配，忽略大小写）
        3. section 名称包含章节标题中的关键维度词
        """
        heading_clean = heading.strip()
        section_clean = section_name.strip()
        if not section_clean:
            return False
        if heading_clean == section_clean:
            return True
        if section_clean.lower() in heading_clean.lower():
            return True
        if heading_clean.lower() in section_clean.lower():
            return True
        return False

    @staticmethod
    def _find_charts_for_heading(heading: str, section_chart_map: Dict[str, List[Dict[str, str]]]) -> List[Dict[str, str]]:
        """根据章节标题从 section_chart_map 中找到所有匹配的配图。"""
        matched: List[Dict[str, str]] = []
        for section_name, charts in section_chart_map.items():
            if ReportService._match_section(heading, section_name):
                matched.extend(charts)
        return matched

    @staticmethod
    def _collect_unmatched_charts(
        chart_images: List[Dict[str, str]],
        section_chart_map: Dict[str, List[Dict[str, str]]],
        matched_sections: set,
    ) -> List[Dict[str, str]]:
        """收集未被章节匹配的配图，用于在文档末尾兜底插入。

        包括：
        - 没有 section 字段的配图
        - section 字段存在但未在任何章节中匹配到的配图
        """
        unmatched = []
        if not chart_images:
            return unmatched
        for ci in chart_images:
            section = (ci.get("section") or "").strip()
            if not section:
                unmatched.append(ci)
            elif section not in matched_sections:
                unmatched.append(ci)
        return unmatched

    def _add_chart_to_docx(self, doc, ci: Dict[str, str], width_inches: float = 5.5):
        """向 docx 文档中插入一张配图。"""
        doc.add_heading(ci.get("title", "图表"), 3)
        try:
            img_data = io.BytesIO(base64.b64decode(ci["base64"]))
            doc.add_picture(img_data, width=docx.shared.Inches(width_inches))
        except Exception as e:
            logger.warning("Failed to insert chart image into docx: %s", e)

    def _add_chart_to_pdf_story(self, story, ci: Dict[str, str], h2_style, width_px: int = 450):
        """向 PDF story 中插入一张配图，返回创建的临时文件路径列表（用于清理）。"""
        import tempfile
        story.append(Paragraph(ci.get("title", "图表"), h2_style))
        try:
            img_data = io.BytesIO(base64.b64decode(ci["base64"]))
        except Exception:
            return []
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp.write(img_data.getvalue())
        tmp.flush()
        tmp_path = tmp.name
        tmp.close()
        story.append(RLImage(tmp_path, width=width_px, height=int(width_px * 0.6)))
        story.append(Spacer(1, 10))
        return [tmp_path]

    def _add_chart_to_pptx_slide(self, prs, ci: Dict[str, str]):
        """为单张配图创建一张空白幻灯片并插入图片。"""
        blank_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank_layout)
        # 添加图表标题
        left = docx.shared.Inches(1)
        top = docx.shared.Inches(0.5)
        txBox = slide.shapes.add_textbox(left, top, docx.shared.Inches(8), docx.shared.Inches(0.8))
        txBox.text_frame.text = ci.get("title", "图表")
        txBox.text_frame.paragraphs[0].font.size = docx.shared.Pt(18)
        txBox.text_frame.paragraphs[0].font.bold = True
        # 插入图片
        try:
            img_data = io.BytesIO(base64.b64decode(ci["base64"]))
            slide.shapes.add_picture(
                img_data,
                docx.shared.Inches(1), docx.shared.Inches(1.5),
                width=docx.shared.Inches(8),
            )
        except Exception as e:
            logger.warning("Failed to insert chart image into pptx: %s", e)

    def generate_docx(self, report: Report, chart_images: List[Dict[str, str]] = None) -> bytes:
        """从 Markdown 报告生成 DOCX 文件，标题层级自动映射为 Word 样式。

        配图插入逻辑：
        - 如果 chart_images 中配图带有 section 字段，则按 section 匹配章节标题，
          在对应章节内容结束后插入配图（宽度 5.5 英寸 ≈ 页面宽度 80%）。
        - 如果配图没有 section 字段或未能匹配到任何章节，则在文档末尾统一插入（向后兼容）。
        """
        doc = docx.Document()
        doc.add_heading(report.title, 0)
        doc.add_heading("执行摘要", 1)
        doc.add_paragraph(report.summary or "无摘要")
        doc.add_heading("详细内容", 1)

        # 构建 section -> charts 映射
        section_chart_map = self._build_section_chart_map(chart_images)
        matched_sections: set = set()  # 记录已匹配到章节的 section 名称

        # 按章节分割 Markdown 内容
        content = report.content_markdown or ""
        # 使用正则按 ## 级标题分割，保留标题行
        sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)

        for section_text in sections:
            section_text = section_text.strip()
            if not section_text:
                continue

            lines = section_text.split("\n")
            current_heading = None

            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                if line_stripped.startswith("# "):
                    doc.add_heading(line_stripped[2:], 1)
                elif line_stripped.startswith("## "):
                    heading_text = line_stripped[3:]
                    current_heading = heading_text
                    doc.add_heading(heading_text, 2)
                elif line_stripped.startswith("### "):
                    doc.add_heading(line_stripped[4:], 3)
                else:
                    doc.add_paragraph(line_stripped)

            # 章节内容结束后，检查是否有匹配的配图
            if current_heading and section_chart_map:
                matched_charts = self._find_charts_for_heading(current_heading, section_chart_map)
                if matched_charts:
                    for ci in matched_charts:
                        self._add_chart_to_docx(doc, ci, width_inches=5.5)
                    # 记录已匹配的 section
                    for ci in matched_charts:
                        s = (ci.get("section") or "").strip()
                        if s:
                            matched_sections.add(s)

        # 兜底：未匹配的配图在文档末尾统一插入（向后兼容）
        unmatched_charts = self._collect_unmatched_charts(chart_images, section_chart_map, matched_sections)
        if unmatched_charts:
            doc.add_heading("数据可视化图表", 1)
            for ci in unmatched_charts:
                self._add_chart_to_docx(doc, ci, width_inches=5.5)

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf.getvalue()

    def generate_pptx(self, report: Report, chart_images: List[Dict[str, str]] = None, template_id: str = None) -> bytes:
        """从报告生成 PPTX 文件。

        优先使用 PPTTemplateService 基于母版模板填充；当 template_id 为 None 或无
        任何模板可用时回退到旧的"裸版式"生成逻辑，保持向后兼容。

        Args:
            report: 报告 ORM 对象
            chart_images: 配图列表
            template_id: 模板 ID（与 MANIFEST.json 中 id 对应，如 "template1"）
        """
        try:
            svc = PPTTemplateService()
            templates = svc.list_templates()
            chosen_id = template_id
            if not chosen_id and templates:
                chosen_id = templates[0].id
            if chosen_id and svc.get_template(chosen_id):
                return svc.fill_template(chosen_id, report, chart_images)
        except Exception as e:
            logger.warning("PPTTemplateService failed (%s), falling back to legacy pptx", e)

        # 兜底：保留旧版实现（无模板或模板服务失败时使用）
        return self._generate_pptx_legacy(report, chart_images)

    def _generate_pptx_legacy(self, report: Report, chart_images: List[Dict[str, str]] = None) -> bytes:
        """旧版 PPTX 生成逻辑（无母版模板时使用）

        配图插入逻辑：
        - 对于每个维度章节，创建一张幻灯片包含标题和文本内容
        - 如果该章节有匹配的配图（根据 section 字段），在文本下方插入配图，
          或创建单独的幻灯片展示配图
        - 图片宽度设置为 8 英寸，位置在 (1, 1.5) 英寸处
        - 如果配图没有 section 字段或未能匹配到任何章节，则在文档末尾统一插入（向后兼容）
        """
        prs = Presentation()
        title_slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_slide_layout)
        slide.shapes.title.text = report.title
        if len(slide.placeholders) > 1:
            slide.placeholders[1].text = report.summary or ""

        # 构建 section -> charts 映射
        section_chart_map = self._build_section_chart_map(chart_images)
        matched_sections: set = set()

        content = report.content_markdown or ""
        sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)
        content_slide_layout = prs.slide_layouts[1]

        for section_text in sections:
            section_text = section_text.strip()
            if not section_text:
                continue

            lines = section_text.split("\n")
            heading = lines[0].strip()
            if heading.startswith("## "):
                heading = heading[3:]
            else:
                # 不是 ## 开头的跳过
                continue

            # 创建内容幻灯片
            slide = prs.slides.add_slide(content_slide_layout)
            slide.shapes.title.text = heading
            body = slide.placeholders[1]
            tf = body.text_frame
            tf.clear()

            # 添加文本内容
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                p = tf.add_paragraph()
                p.text = line

            # 检查是否有匹配的配图
            if section_chart_map:
                matched_charts = self._find_charts_for_heading(heading, section_chart_map)
                if matched_charts:
                    # 为每张匹配的配图创建单独的幻灯片
                    for ci in matched_charts:
                        self._add_chart_to_pptx_slide(prs, ci)
                    # 记录已匹配的 section
                    for ci in matched_charts:
                        s = (ci.get("section") or "").strip()
                        if s:
                            matched_sections.add(s)

        # 兜底：未匹配的配图在末尾统一插入（向后兼容）
        unmatched_charts = self._collect_unmatched_charts(chart_images, section_chart_map, matched_sections)
        if unmatched_charts:
            for ci in unmatched_charts:
                self._add_chart_to_pptx_slide(prs, ci)

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

        字体选择（按优先级探测,任意一个存在即采用）：
        - Linux(Docker): 文泉驿微米黑 (WenQuanYi Micro Hei) — apt-get install fonts-wqy-microhei
        - Windows:      微软雅黑 (msyh.ttc) / 黑体 (simhei.ttf) / 宋体 (simsun.ttc) / 楷体 (simkai.ttf)
        - macOS:        PingFang.ttc / STHeiti Medium.ttc / 苹方
        """
        font_paths = [
            # Linux(Docker 部署环境)
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            # Windows(本地开发)
            "C:/Windows/Fonts/msyh.ttc",          # 微软雅黑
            "C:/Windows/Fonts/msyhbd.ttc",        # 微软雅黑 Bold
            "C:/Windows/Fonts/simhei.ttf",        # 黑体
            "C:/Windows/Fonts/simsun.ttc",        # 宋体
            "C:/Windows/Fonts/simkai.ttf",        # 楷体
            "C:/Windows/Fonts/STSONG.TTF",        # 华文宋体
            "C:/Windows/Fonts/SIMYOU.TTF",        # 幼圆
            # macOS(本地开发)
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/Library/Fonts/Songti.ttc",
        ]
        cjk_font_name = None
        cjk_font_path = None
        for path in font_paths:
            try:
                if not os.path.exists(path):
                    continue
                pdfmetrics.registerFont(TTFont('WQYMicroHei', path))
                cjk_font_name = 'WQYMicroHei'
                cjk_font_path = path
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
            logging.getLogger(__name__).warning(
                "No CJK font found in known paths; PDF will use default font and may show garbled CJK. "
                "Searched: %s",
                font_paths,
            )

        return styles

    def generate_pdf(self, report: Report, chart_images: List[Dict[str, str]] = None) -> bytes:
        """从 Markdown 报告生成 PDF 文件,支持中文字体。

        配图插入逻辑：
        - 如果 chart_images 中配图带有 section 字段，则按 section 匹配章节标题，
          在对应章节内容结束后插入配图（宽度 450 像素）。
        - 如果配图没有 section 字段或未能匹配到任何章节，则在文档末尾统一插入（向后兼容）。

        鲁棒性说明:
        - Markdown 行经 HTML 转义后再交给 reportlab Paragraph(避免 < / > / & 触发 XMLSyntaxError)
        - 当某行无法被 reportlab 解析时,降级为纯文本 Paragraph
        - 行内的图片/表格语法会被静默跳过(避免垃圾段落)
        """
        from xml.sax.saxutils import escape as _xml_escape

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        styles = self._get_cjk_stylesheet()
        t_style = styles['Title']
        h1_style = styles['Heading1']
        h2_style = styles['Heading2']
        body_style = styles['BodyText']

        def _safe_paragraph(text: str, style):
            """把字符串安全地放到 Paragraph;先转义 XML 特殊字符;失败时再二次降级。"""
            escaped = _xml_escape(text)
            try:
                return Paragraph(escaped, style)
            except Exception:
                return Paragraph(escaped.replace("<", "").replace(">", ""), style)

        story = [_safe_paragraph(report.title, t_style), Spacer(1, 20)]
        story.append(_safe_paragraph("执行摘要", h1_style))
        story.append(_safe_paragraph(report.summary or "无", body_style))
        story.append(Spacer(1, 15))

        story.append(_safe_paragraph("详细内容", h1_style))

        # 构建 section -> charts 映射
        section_chart_map = self._build_section_chart_map(chart_images)
        matched_sections: set = set()
        tmp_paths: List[str] = []

        # 按章节分割 Markdown 内容
        content = report.content_markdown or ""
        sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)

        for section_text in sections:
            section_text = section_text.strip()
            if not section_text:
                continue

            lines = section_text.split("\n")
            current_heading = None

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue
                # 跳过 markdown 行内图片语法 ![alt](url)
                if line.startswith("![") and "](http" in line:
                    alt = line.split("]", 1)[0][2:] or "未命名"
                    story.append(_safe_paragraph(f"[图片: {alt}]", body_style))
                    continue
                # 跳过纯水平分割线
                if re.fullmatch(r"[-*_]{3,}", line):
                    continue
                if line.startswith("# "):
                    story.append(Spacer(1, 10))
                    story.append(_safe_paragraph(line[2:], h1_style))
                elif line.startswith("## "):
                    current_heading = line[3:]
                    story.append(Spacer(1, 8))
                    story.append(_safe_paragraph(current_heading, h2_style))
                else:
                    story.append(_safe_paragraph(line, body_style))
                    story.append(Spacer(1, 4))

            # 章节内容结束后，检查是否有匹配的配图
            if current_heading and section_chart_map:
                matched_charts = self._find_charts_for_heading(current_heading, section_chart_map)
                if matched_charts:
                    for ci in matched_charts:
                        paths = self._add_chart_to_pdf_story(story, ci, h2_style, width_px=450)
                        tmp_paths.extend(paths)
                    for ci in matched_charts:
                        s = (ci.get("section") or "").strip()
                        if s:
                            matched_sections.add(s)

        # 兜底：未匹配的配图在文档末尾统一插入（向后兼容）
        unmatched_charts = self._collect_unmatched_charts(chart_images, section_chart_map, matched_sections)
        if unmatched_charts:
            story.append(_safe_paragraph("数据可视化图表", h1_style))
            for ci in unmatched_charts:
                paths = self._add_chart_to_pdf_story(story, ci, h2_style, width_px=450)
                tmp_paths.extend(paths)

        doc.build(story)

        # 清理图表临时文件
        for tp in tmp_paths:
            try:
                os.unlink(tp)
            except OSError:
                pass

        buf.seek(0)
        return buf.getvalue()

    def generate_markdown(self, report: Report) -> bytes:
        """直接返回 Markdown 原始内容，供下载"""
        content = f"# {report.title}\n\n## 执行摘要\n{report.summary or '无'}\n\n## 详细内容\n{report.content_markdown or ''}"
        return content.encode("utf-8")

    async def export_report(
        self, session: AsyncSession, report_id: int, fmt: str, template_id: Optional[str] = None
    ) -> Tuple[str, str, bytes]:
        """
        统一导出入口

        返回三元组：(文件名, MIME类型, 文件二进制内容)
        路由函数据此设置 HTTP 响应头（Content-Disposition + Content-Type）

        Args:
            template_id: PPT 母版模板 ID（仅 fmt=pptx 时生效），None 时取第一套可用模板

        注意：lazy 模式下不在此处触发 Milvus 写入；
        写入由路由层在调用本方法前通过 `upload_to_vector_store_if_pending()` 触发。
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
            data = self.generate_pptx(r, chart_images=chart_images, template_id=template_id)
            result = (f"report_{r.id}.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", data)
        elif fmt == "md" or fmt == "markdown":
            result = (f"report_{r.id}.md", "text/markdown", self.generate_markdown(r))
        else:
            raise ValueError("Unsupported format. Use docx, pdf, pptx, or md.")

        return result
