import io
from typing import List, Optional, Tuple
import docx
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
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

    def generate_pdf(self, report: Report) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        styles = getSampleStyleSheet()
        t_style = styles['Title']
        h1_style = styles['Heading1']
        h2_style = styles['Heading2']
        body_style = styles['BodyText']

        story = [Paragraph(report.title, t_style), Spacer(1, 20)]
        story.append(Paragraph("Executive Summary / 摘要", h1_style))
        story.append(Paragraph(report.summary or "N/A", body_style))
        story.append(Spacer(1, 15))

        story.append(Paragraph("Detailed Analysis / 详细内容", h1_style))
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
        content = f"# {report.title}\n\n## 执行摘要\n{report.summary or '无'}\n\n## 详细内容\n{report.content_markdown or ''}"
        return content.encode("utf-8")

    async def export_report(self, session: AsyncSession, report_id: int, fmt: str) -> Tuple[str, str, bytes]:
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
