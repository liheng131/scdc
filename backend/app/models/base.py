"""
ORM 基类模块

提供所有数据库模型共享的基础类：
- Base: SQLAlchemy DeclarativeBase 基类，用于自动发现和映射模型
- TimestampMixin: 时间戳混入类，自动管理 created_at 和 updated_at 字段

为什么使用 Mixin 模式：
- 每个表都需要创建时间和更新时间，Mixin 避免在每个模型文件中重复定义
- 配合 SQLAlchemy 的 default 和 onupdate 参数，无需手动赋值
"""

from datetime import datetime
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    """所有 ORM 模型的基类，SQLAlchemy 通过此基类自动发现表定义"""
    pass

class TimestampMixin:
    """
    自动时间戳混入类

    - created_at: 记录创建时自动填充当前时间
    - updated_at: 每次更新自动刷新为当前时间（由数据库端 func.now() 保证）
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )
