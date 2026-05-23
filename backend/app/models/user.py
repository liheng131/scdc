"""
用户模型

定义 users 表结构，存储系统用户的基本信息和权限角色。

角色设计（UserRole）：
- admin: 管理员，拥有全部操作权限
- analyst: 分析师，可创建任务、查看报告和发起分析
- viewer: 浏览者，只读权限，仅可查看共享的报告

status 字段用于启用/禁用用户，而非直接删除记录。
"""

import enum
from sqlalchemy import String, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class UserRole(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.viewer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
