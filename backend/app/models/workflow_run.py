from typing import Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class StageState:
    """阶段状态枚举（不直接用 StrEnum，便于跨 Python 版本兼容）"""
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    current_stage: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    stages_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 历史追问聚合 spec: 追问工作流指向其父工作流的 workflow_id
    # 顶层对话 parent_workflow_id = NULL,追问对话 parent_workflow_id = 父的 workflow_id
    parent_workflow_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    # Phase 2 Human-in-the-Loop：阶段状态机 + 输出 + 历史
    # Spec 1: 数据采集阶段确认
    stage_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StageState.RUNNING, server_default=StageState.RUNNING
    )
    stage_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stage_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)