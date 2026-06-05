"""
用户服务

封装用户创建、唯一性校验等业务逻辑。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.schemas.auth import RegisterIn


class EmailTakenError(Exception):
    """邮箱已被注册"""


class UsernameTakenError(Exception):
    """用户名已被注册"""


async def create_user(db: AsyncSession, payload: RegisterIn) -> User:
    """
    创建一个新用户

    校验邮箱 / 用户名唯一性，密码用 bcrypt 哈希。
    抛 EmailTakenError / UsernameTakenError 由路由层映射 409。
    """
    # 唯一性校验
    email_row = await db.execute(select(User).where(User.email == payload.email))
    if email_row.scalars().first():
        raise EmailTakenError()
    uname_row = await db.execute(select(User).where(User.username == payload.username))
    if uname_row.scalars().first():
        raise UsernameTakenError()

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        role=UserRole.viewer,
        status="active",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
