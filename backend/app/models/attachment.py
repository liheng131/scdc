"""
附件模型

定义 attachments 表，存储用户上传的附件元数据与解析结果。

设计要点：
- id 使用 UUID 字符串，便于在前端展示与跨服务引用
- file_hash 为 sha256 十六进制摘要，与 user_id 一起作为去重键，
  同一用户上传相同内容会复用旧记录，避免重复解析
- minio_object_key 指向对象存储中的实际文件路径
- parsed_content / parsed_chunks 持久化解析结果，避免每次重新解析
- extra_metadata 使用列名 `metadata` 避开 SQLAlchemy 内建属性
"""

from typing import Optional
from sqlalchemy import String, Text, Integer, JSON, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # pdf/markdown/txt/image/...
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)  # bytes
    file_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # sha256 hex
    minio_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    parsed_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parsed_chunks: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
