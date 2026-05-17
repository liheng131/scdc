from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class NotificationRuleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    channel: str = Field(..., max_length=50, description="'email' 或 'webhook'")
    trigger: str = Field(..., max_length=100, description="如 'report_ready', 'event_alert'")
    target: str = Field(..., max_length=255, description="邮箱地址或 Webhook URL")
    enabled: bool = Field(default=True)

class NotificationRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    channel: Optional[str] = Field(None, max_length=50)
    trigger: Optional[str] = Field(None, max_length=100)
    target: Optional[str] = Field(None, max_length=255)
    enabled: Optional[bool] = None

class NotificationRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    channel: str
    trigger: str
    target: str
    enabled: bool
