"""
报告 Schema 模块

定义报告创建、更新、查询的数据校验结构。

version 字段支持报告版本管理，draft/published/archived 状态用于发布工作流。
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class ReportCreate(BaseModel):
    task_id: int
    title: str = Field(..., max_length=255)
    version: str = Field(default="v1.0", max_length=20)
    status: str = Field(default="draft", max_length=50)
    summary: Optional[str] = None
    content_markdown: Optional[str] = None
    storage_ref: Optional[str] = None

class ReportUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    version: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=50)
    summary: Optional[str] = None
    content_markdown: Optional[str] = None
    storage_ref: Optional[str] = None

class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    title: str
    version: str
    status: str
    summary: Optional[str]
    content_markdown: Optional[str]
    storage_ref: Optional[str]
    created_at: datetime
    updated_at: datetime
