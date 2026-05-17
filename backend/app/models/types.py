import json
from sqlalchemy.types import TypeDecorator, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

class JSONB(TypeDecorator):
    """跨数据库兼容的 JSONB 数据类型。
    在 PostgreSQL 下使用原生 JSONB，在 SQLite 等其他库下退化为内置 JSON/Text。
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())
