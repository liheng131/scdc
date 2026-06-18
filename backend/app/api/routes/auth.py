"""
认证（Auth）API 路由

提供基于 OAuth2 Password Flow 的登录认证端点。
前端通过 POST /api/v1/auth/login/access-token 提交 username + password，
服务端验密成功后返回 JWT access_token。

为什么使用 OAuth2PasswordRequestForm：
- FastAPI 内置的 OAuth2 表单解析器，自动处理 application/x-www-form-urlencoded
- 与 Swagger UI 的 Authorize 按钮联动，便于在线测试
"""

import time
from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.api.deps import get_current_active_user
from app.api.responses import success_response, ResponseModel
from app.schemas.auth import RegisterIn
from app.services.captcha import generate_captcha, validate_captcha
from app.services.user import (
    create_user,
    EmailTakenError,
    UsernameTakenError,
)

router = APIRouter()

@router.post("/login/access-token")
async def login_access_token(
    db: Annotated[AsyncSession, Depends(get_db)],
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    """
    OAuth2 兼容的令牌登录接口

    接受 username 或 email 作为 identifier：
    - 若含 '@' 则按 email 列查 users
    - 否则按 username 列查
    - 错误消息统一为 "Incorrect email or password"（不区分原因）
    """
    identifier = form_data.username
    if "@" in identifier:
        stmt = select(User).where(User.email == identifier)
    else:
        stmt = select(User).where(User.username == identifier)
    result = await db.execute(stmt)
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


# === 极简 IP 限流（避免引入 slowapi 依赖） ===
_RATE_LIMIT_BUCKET: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 60.0   # 1 分钟窗口
_RATE_LIMIT_MAX = 10        # 最多 10 次


def _check_rate_limit(client_ip: str) -> bool:
    """返回 True 表示允许，False 表示被限流"""
    now = time.time()
    arr = _RATE_LIMIT_BUCKET.setdefault(client_ip, [])
    # 清理过期时间戳
    while arr and now - arr[0] > _RATE_LIMIT_WINDOW:
        arr.pop(0)
    if len(arr) >= _RATE_LIMIT_MAX:
        return False
    arr.append(now)
    return True


@router.get("/captcha", response_model=ResponseModel)
async def get_captcha(request: Request):
    """
    拉取数学验证（注册时使用）

    返回 { token, question }，token 5 分钟内有效，一次性消费。
    限流：同 IP 1 分钟最多 10 次。
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    data = generate_captcha()
    # 不向客户端泄露 answer
    return success_response(data={"token": data["token"], "question": data["question"]})


@router.post("/register", response_model=ResponseModel, status_code=201)
async def register(
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: RegisterIn,
):
    """
    账号注册

    校验顺序：
    1. 验证答案（一次性消费）
    2. Pydantic 字段级（已自动跑：email / username 字符 / password 强度 / 一致性）
    3. 唯一性 → 抛 EmailTakenError / UsernameTakenError
    4. 创建 user（role=viewer, status=active）
    """
    # 1. captcha 验证
    if not validate_captcha(payload.captcha_token, payload.captcha_answer):
        raise HTTPException(status_code=400, detail="INVALID_CAPTCHA")

    # 2-4. 唯一性 + 创建
    try:
        user = await create_user(db, payload)
    except EmailTakenError:
        raise HTTPException(status_code=409, detail="EMAIL_TAKEN")
    except UsernameTakenError:
        raise HTTPException(status_code=409, detail="USERNAME_TAKEN")

    return success_response(data={
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })


@router.get("/me", response_model=ResponseModel)
async def read_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    获取当前登录用户信息

    用途：
    - 前端应用初始化（main.ts）调用,验证 token 有效性
    - 前端 onMounted 调以确认 fresh user state（Phase 7 修复 stale token 用）
    - token 失效时依赖 get_current_active_user 自动 401,前端 client.ts 会清 token + 触发重登

    返回字段与登录响应中的 user 字段保持一致,前端可以无差别使用。
    """
    return success_response(data={
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        "status": current_user.status,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    })
