"""
采集记录 Schema 模块

定义采集记录的创建、更新和响应数据结构。
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class CollectedRecordCreate(BaseModel):
    title: str
    url: Optional[str] = None
    content: Optional[str] = None
    source_type: str = "web"

class CollectedRecordUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None
    source_type: Optional[str] = None

class CollectedRecordOut(BaseModel):
    id: int
    data_source_id: int
    title: str
    url: Optional[str] = None
    content: Optional[str] = None
    source_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True