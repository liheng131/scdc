"""add_report_images_column

Revision ID: add_images_to_reports
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa

revision = "add_images_to_reports"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("images", sa.JSON, nullable=True, comment="配图列表"))


def downgrade() -> None:
    op.drop_column("reports", "images")
