"""add_html_ppt_fields_to_reports

Phase 1 of html-ppt-workflow-report spec:
- page_model: 结构化 PageModel 列表（ReporterAgent 直接产出）
- theme: html-ppt 主题名（36 套之一，默认 minimal-white）
- notes_summary: 整份报告执行摘要（演讲者模式开篇用）

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "page_model",
            sa.JSON,
            nullable=True,
            comment="html-ppt 结构化页面描述（List[PageModel]）",
        ),
    )
    op.add_column(
        "reports",
        sa.Column(
            "theme",
            sa.String(length=50),
            nullable=True,
            server_default="minimal-white",
            comment="html-ppt 主题名",
        ),
    )
    op.add_column(
        "reports",
        sa.Column(
            "notes_summary",
            sa.Text,
            nullable=True,
            comment="整份报告的 150 字以内执行摘要",
        ),
    )


def downgrade() -> None:
    op.drop_column("reports", "notes_summary")
    op.drop_column("reports", "theme")
    op.drop_column("reports", "page_model")
