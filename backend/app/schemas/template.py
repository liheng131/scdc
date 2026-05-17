from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class TemplateCreate(BaseModel):
    name: str = Field(..., max_length=100)
    scope: str = Field(..., max_length=50, description="'report', 'prompt', 'notification'")
    version: str = Field(default="v1.0", max_length=20)
    content: str = Field(...)
    status: str = Field(default="active", max_length=50)

class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    scope: Optional[str] = Field(None, max_length=50)
    version: Optional[str] = Field(None, max_length=20)
    content: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)

class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scope: str
    version: str
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
