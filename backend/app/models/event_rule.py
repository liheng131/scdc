from typing import Optional, List
from sqlalchemy import String, ForeignKey, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin
from app.models.types import JSONB

class EventRule(Base, TimestampMixin):
    __tablename__ = "event_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False) # "webhook", "keyword", "metric"
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
