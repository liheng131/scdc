"""add_html_content_to_reports

Add html_content column to reports table for storing complete HTML presentation.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "html_content",
            sa.Text,
            nullable=True,
            comment="完整的 HTML 演示文稿内容",
        ),
    )


def downgrade() -> None:
    op.drop_column("reports", "html_content")
