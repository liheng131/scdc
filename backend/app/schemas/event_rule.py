"""
事件规则 Schema 模块

定义事件监听与自动触发规则的数据校验结构。
"""

from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

class EventRuleCreate(BaseModel):
    name: str = Field(..., max_length=150)
    event_type: str = Field(..., max_length=50)
    keywords: List[str] = Field(default=[])
    threshold: Optional[float] = None
    target_topic: str = Field(..., max_length=200)
    is_active: bool = Field(default=True)

class EventRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    event_type: Optional[str] = Field(None, max_length=50)
    keywords: Optional[List[str]] = None
    threshold: Optional[float] = None
    target_topic: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None

class EventRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    event_type: str
    keywords: List[str]
    threshold: Optional[float]
    target_topic: str
    is_active: bool
    created_by: int
