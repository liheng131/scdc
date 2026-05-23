"""
采集记录模型

定义 collected_records 表，存储数据源手动抓取的资讯条目。
每条记录关联一个 data_source，记录标题、URL、正文内容等信息。

为什么独立建表而非内嵌 JSON：
- 需要支持分页查询和按数据源筛选
- 每条记录支持独立 CRUD（查看/编辑/删除）
- 后续可扩展添加标签、分类、已读状态等字段
"""

from sqlalchemy import String, Text, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class CollectedRecord(Base, TimestampMixin):
    __tablename__ = "collected_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="web", nullable=False)

    data_source: Mapped["DataSource"] = relationship("DataSource", backref="collected_records")