"""
数据源模型

定义 data_sources 表，存储外部数据接入配置（搜素引擎、RSS、API 等）。

config 字段使用 JSONB 存储任意结构的连接配置，支持不同数据源类型的自定义参数。
schedule 字段用于定时拉取，enabled 控制数据源启用状态（停用而非删除）。
"""

from typing import Any, Dict
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin
from app.models.types import JSONB

class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    schedule: Mapped[str] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="idle", nullable=False)
