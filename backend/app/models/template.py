"""
模板模型

定义 templates 表，存储可复用的内容模板。

scope 字段区分模板用途：
- report: 报告模板（定义报告的章节结构和格式）
- prompt: Prompt 模板（定义发送给 LLM 的提示词模板）
- notification: 通知模板（定义邮件/Webhook 通知的格式）

为什么使用模板：
- 将 Prompt 和报告格式与代码解耦，非技术人员也可修改
- 支持版本管理，不同版本可并存、回滚
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class Template(Base, TimestampMixin):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="v1.0", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
