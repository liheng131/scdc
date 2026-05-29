from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AiModelConfig(Base, TimestampMixin):
    __tablename__ = "ai_model_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    model_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="llm")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)