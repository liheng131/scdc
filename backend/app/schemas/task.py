"""
任务 Schema 模块

定义任务创建、更新、查询的 Pydantic 数据模型。

Schema 命名约定：
- Base: 共享的基础字段
- Create: 用于 POST 创建请求
- Update: 用于 PUT/PATCH 更新请求（所有字段可选）
- Out: 用于 GET 响应，包含 id、时间戳等只读字段
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

class TaskBase(BaseModel):
    name: str = Field(..., max_length=200)
    type: str = Field(default="deep", max_length=50)  # quick / deep / monthly
    trigger_mode: str = Field(default="manual", max_length=50)  # manual / qa / schedule
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_ref: Optional[str] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, max_length=50)
    output_ref: Optional[str] = None

class TaskRunBase(BaseModel):
    stage: str = Field(..., max_length=50)
    status: str = Field(default="pending", max_length=50)

class TaskRunCreate(TaskRunBase):
    task_id: int

class TaskRunUpdate(BaseModel):
    status: Optional[str] = Field(None, max_length=50)
    ended_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = Field(None, max_length=500)

class TaskRunOut(TaskRunBase):
    id: int
    task_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

class TaskOut(TaskBase):
    id: int
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    runs: Optional[List[TaskRunOut]] = None

    class Config:
        from_attributes = True
