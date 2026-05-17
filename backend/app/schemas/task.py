from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

class TaskBase(BaseModel):
    name: str = Field(..., max_length=200)
    type: str = Field(default="deep", max_length=50) # 'quick', 'deep', 'monthly'
    trigger_mode: str = Field(default="manual", max_length=50) # 'manual', 'qa', 'schedule'
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
