"""
通知规则模型

定义 notification_rules 表，配置系统的通知渠道和触发条件。

channel: 通知渠道（email / webhook）
trigger: 触发条件（report_ready / event_alert 等）
target: 通知接收目标（邮箱地址或 Webhook URL）
enabled: 可单独启停某条规则，无需删除
"""

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class NotificationRule(Base, TimestampMixin):
    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
