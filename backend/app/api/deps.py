"""
FastAPI 依赖注入模块（Dependencies）

职责：
- 提供三级用户认证依赖：普通用户 → 活跃用户 → 管理员
- JWT 令牌从 Authorization: Bearer <token> 请求头中提取
- 解码后从数据库中加载用户对象，验证账号状态和角色权限
- 额外提供 SSE 兼容认证，支持从查询参数 ?token=xxx 读取令牌

设计的依赖链：
  get_current_user   （解析 JWT → 查库获取用户）
    ↓
  get_current_active_user （检查 status == "active"）
    ↓
  get_current_admin_user   （检查 role == "admin"）

SSE 认证：
  get_current_active_user_sse （优先 Header，回退 Query 参数）
    ↓
  继承 get_current_active_user 的活跃状态检查逻辑

使用者只需声明所需的最高级别依赖即可自动完成所有校验。
"""

from typing import AsyncGenerator, Annotated, Optional
import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import Depends, HTTPException, status, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import UnauthorizedException
from app.core.security import ALGORITHM
from app.models.user import User
from app.schemas.user import TokenPayload

# OAuth2 密码承载令牌提取器
# FastAPI 自动从请求头 Authorization: Bearer <token> 中提取 token 字符串
# tokenUrl 指向 Swagger UI 中的登录端点，便于在线调试时自动获取令牌
# auto_error=False: SSE 端点无法传 Header，需回退到 Query 参数，不使用 OAuth2 自动报错
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/access-token", auto_error=False)

async def _verify_token_and_get_user(token: str, db: AsyncSession) -> User:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError:
        raise UnauthorizedException(message="Could not validate credentials")

    result = await db.execute(select(User).where(User.id == int(token_data.sub)))
    user = result.scalars().first()

    if not user:
        raise UnauthorizedException(message="User not found")
    return user

async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    """
    解析 JWT 令牌并从数据库加载当前用户

    步骤：
    1. 从 Authorization Bearer 头中提取 raw token
    2. 用 secret_key 和 HS256 算法解码 JWT，提取 sub（用户 ID）
    3. 在数据库中查询该用户
    4. 若令牌无效或用户不存在，抛出 UnauthorizedException
    """
    return await _verify_token_and_get_user(token, db)

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    获取当前活跃用户

    在 get_current_user 基础上额外检查账号状态（status == "active"），
    防止已禁用或冻结的账号继续访问系统。
    """
    if current_user.status != "active":
        raise UnauthorizedException(message="Inactive user")
    return current_user

async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    """
    获取当前管理员用户

    在 get_current_active_user 基础上额外检查角色（role == "admin"），
    用于保护只有管理员才能调用的敏感 API（如用户管理、系统配置）。
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges"
        )
    return current_user


async def get_current_user_sse(
    db: Annotated[AsyncSession, Depends(get_db)],
    header_token: Annotated[Optional[str], Depends(oauth2_scheme)] = None,
    query_token: Annotated[Optional[str], Query(alias="token")] = None,
) -> User:
    """
    SSE 兼容的 JWT 认证依赖

    优先从 Authorization Header 读取 token，回退到查询参数 ?token=xxx。
    EventSource API 不支持自定义请求头，只能通过 URL 传递令牌。
    """
    token = header_token or query_token
    if not token:
        raise UnauthorizedException(message="Not authenticated")
    return await _verify_token_and_get_user(token, db)


async def get_current_active_user_sse(
    current_user: Annotated[User, Depends(get_current_user_sse)]
) -> User:
    """
    SSE 兼容的活跃用户认证

    在 get_current_user_sse 基础上额外检查账号状态。
    """
    if current_user.status != "active":
        raise UnauthorizedException(message="Inactive user")
    return current_user
