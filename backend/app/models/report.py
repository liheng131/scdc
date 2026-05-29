"""
报告模型

定义 reports 表，存储 AI 分析产出的结构化报告。

设计要点：
- task_id 外键关联到 tasks 表，一个任务可产生多个版本的报告
- version 字段支持报告版本迭代（v1.0, v2.0…）
- content_markdown 存储 Markdown 格式的完整报告正文
- storage_ref 预留字段，用于指向外部存储（如 S3 / MinIO）中的导出文件路径
"""

from typing import Optional
from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class Report(Base, TimestampMixin):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="v1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    images: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="配图列表")
