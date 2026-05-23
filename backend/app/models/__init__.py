"""
数据库模型模块（SQLAlchemy ORM）

集中导出所有数据库模型，便于 Alembic 迁移脚本和业务代码统一引用。
每个模型文件对应一个数据库表，通过 DeclarativeBase 映射到 PostgreSQL/SQLite。
"""

from app.models.base import Base
from app.models.user import User, UserRole
from app.models.data_source import DataSource
from app.models.collected_record import CollectedRecord
from app.models.task import Task, TaskRun
from app.models.report import Report
from app.models.template import Template
from app.models.notification import NotificationRule
from app.models.event_rule import EventRule

__all__ = [
    "Base",
    "User",
    "UserRole",
    "DataSource",
    "CollectedRecord",
    "Task",
    "TaskRun",
    "Report",
    "Template",
    "NotificationRule",
    "EventRule"
]
