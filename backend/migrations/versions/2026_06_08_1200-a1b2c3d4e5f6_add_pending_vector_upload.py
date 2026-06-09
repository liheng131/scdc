"""add pending_vector_upload and vector_uploaded_at to reports

Revision ID: a1b2c3d4e5f6
Revises: add_images_to_reports
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "add_images_to_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "pending_vector_upload",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否待写入向量库",
        ),
    )
    op.add_column(
        "reports",
        sa.Column(
            "vector_uploaded_at",
            sa.String(length=50),
            nullable=True,
            comment="向量库写入时间 ISO 格式",
        ),
    )
    op.create_index(
        "ix_reports_pending_vector_upload",
        "reports",
        ["pending_vector_upload"],
    )


def downgrade() -> None:
    op.drop_index("ix_reports_pending_vector_upload", table_name="reports")
    op.drop_column("reports", "vector_uploaded_at")
    op.drop_column("reports", "pending_vector_upload")
