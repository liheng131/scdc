"""add parent_workflow_id to workflow_runs

历史追问聚合 spec: 追问工作流通过 parent_workflow_id 关联到父工作流,刷新历史时按父-子折叠展示。

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column(
            "parent_workflow_id",
            sa.String(length=50),
            nullable=True,
            comment="追问工作流的父工作流 ID,顶层对话为 NULL",
        ),
    )
    op.create_index(
        "ix_workflow_runs_parent_workflow_id",
        "workflow_runs",
        ["parent_workflow_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_parent_workflow_id", table_name="workflow_runs")
    op.drop_column("workflow_runs", "parent_workflow_id")
