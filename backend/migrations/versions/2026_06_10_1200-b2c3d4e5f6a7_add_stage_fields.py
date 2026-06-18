"""add stage_state / stage_output / stage_history to workflow_runs

Spec 1: Human-in-the-Loop 数据采集阶段确认

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column(
            "stage_state",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'running'"),
            comment="阶段状态：running/awaiting_confirmation/completed/failed",
        ),
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "stage_output",
            sa.Text(),
            nullable=True,
            comment="当前阶段输出 JSON（待用户确认的内容）",
        ),
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "stage_history",
            sa.Text(),
            nullable=True,
            comment="阶段重试历史 JSON 数组",
        ),
    )
    op.create_index(
        "ix_workflow_runs_stage_state",
        "workflow_runs",
        ["stage_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_stage_state", table_name="workflow_runs")
    op.drop_column("workflow_runs", "stage_history")
    op.drop_column("workflow_runs", "stage_output")
    op.drop_column("workflow_runs", "stage_state")
