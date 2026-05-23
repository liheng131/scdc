"""
定时任务 Schema 模块

定义 Cron 定时分析任务的数据结构。

cron_expr 使用标准 Cron 表达式（如 "0 8 * * *" 表示每天 8:00）。
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.schemas.task import TaskOut

class ScheduleCreate(BaseModel):
    name: str = Field(..., max_length=150)
    topic: str = Field(..., max_length=200)
    cron_expr: str = Field(..., description="标准 Cron 表达式, 例如 '0 8 * * *'")
    max_items: int = Field(default=3, le=10)

class ScheduleOut(BaseModel):
    task_id: int
    name: str
    cron_expr: str
    topic: str
    status: str
    task: Optional[TaskOut] = None
