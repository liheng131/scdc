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
