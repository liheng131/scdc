"""
用户 Schema 模块

定义用户认证和管理的 Pydantic 数据模型。

为什么分离 UserCreate / UserOut：
- UserCreate 包含明文密码（仅在创建时接收，不存储到数据库）
- UserOut 不包含密码字段，防止 API 响应泄露敏感信息
- Config.from_attributes = True 允许从 SQLAlchemy ORM 对象直接构造
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str
    role: str = "viewer"

class UserOut(UserBase):
    id: int
    role: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
