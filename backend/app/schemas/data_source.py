"""
数据源 Schema 模块

定义数据源接入配置的数据校验结构。

AliasChoices("type", "source_type") 实现字段别名：
- 前端可能发送 "source_type" 字段名（兼容旧版 API）
- 后端内部统一使用 "type" 字段名
- 序列化输出时使用 "source_type"（serialization_alias）
"""

from typing import Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, AliasChoices

class DataSourceBase(BaseModel):
    name: str
    type: str = Field(..., validation_alias=AliasChoices("type", "source_type"), serialization_alias="source_type")
    config: Dict[str, Any]
    status: str = "active"

class DataSourceCreate(DataSourceBase):
    pass

class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

class DataSourceOut(DataSourceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
