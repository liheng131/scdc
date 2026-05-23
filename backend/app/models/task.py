"""
任务模型

定义 tasks 和 task_runs 两张表的关系：

- Task（父表）: 记录一次分析任务的元信息（名称、类型、触发方式、输入参数）
- TaskRun（子表）: 记录任务执行过程中每个阶段的运行状态

关系设计：
- Task.task_runs 是一对多关系，级联删除（删除任务时自动清理关联的运行记录）
- trigger_mode 区分手动触发 / 问答式 / 定时任务三种模式
- type 区分 quick（快速分析）/ deep（深度分析）/ monthly（月度报告）三种分析深度

为什么拆分为 Task 和 TaskRun：
- 一个任务可被多次执行（重试、定时触发）
- 每次执行都记录独立的阶段、状态、结果，便于问题回溯
"""

from typing import Any, Dict, Optional
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.types import JSONB

class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # quick / deep / monthly
    trigger_mode: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # manual / qa / schedule
    status: Mapped[str] = mapped_column(String(50), default="created", index=True, nullable=False)
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    runs: Mapped[list["TaskRun"]] = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")

class TaskRun(Base):
    """
    任务运行记录

    stage 字段记录当前执行阶段（queued / collecting / cleaning / analyzing / reporting / completed / failed），
    与 OrchestratorAgent 的状态回调保持一致。
    """
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    task: Mapped[Task] = relationship("Task", back_populates="runs")
