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
from sqlalchemy import String, Text, JSON, Boolean
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
    pending_vector_upload: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, comment="是否待写入向量库")
    vector_uploaded_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="向量库写入时间 ISO 格式")
    # html-ppt 结构化页面（Phase 1 新增）：ReporterAgent 直接产出的结构化 PageModel 列表
    page_model: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=None, comment="html-ppt 结构化页面描述（List[PageModel]）")
    # html-ppt 主题（Phase 1 新增）：36 套主题之一，默认 minimal-white
    theme: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="minimal-white", comment="html-ppt 主题名")
    # 整份报告的执行摘要（演讲者模式开篇用，Phase 1 新增）
    notes_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None, comment="整份报告的 150 字以内执行摘要")
    # 完整 HTML 演示文稿内容（html-ppt 设计系统生成）
    html_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None, comment="完整的 HTML 演示文稿内容")
