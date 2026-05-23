"""
认证（Auth）API 路由

提供基于 OAuth2 Password Flow 的登录认证端点。
前端通过 POST /api/v1/auth/login/access-token 提交 username + password，
服务端验密成功后返回 JWT access_token。

为什么使用 OAuth2PasswordRequestForm：
- FastAPI 内置的 OAuth2 表单解析器，自动处理 application/x-www-form-urlencoded
- 与 Swagger UI 的 Authorize 按钮联动，便于在线测试
"""

from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.api.responses import success_response

router = APIRouter()

@router.post("/login/access-token")
async def login_access_token(
    db: Annotated[AsyncSession, Depends(get_db)],
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    """
    OAuth2 兼容的令牌登录接口

    接收 username + password（通过表单），验证通过后返回：
    - access_token: JWT 令牌
    - token_type: "bearer"（固定值）
    - user: 用户基本信息（id, username, email, role, status）

    前端获取 token 后存入 localStorage，后续请求通过 Authorization: Bearer <token> 携带
    """
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif user.status != "active":
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)

    return success_response(data={
        "access_token": create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "created_at": str(user.created_at),
        }
    })
