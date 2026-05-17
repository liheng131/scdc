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
