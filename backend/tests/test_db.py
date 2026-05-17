import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.base import Base
from app.models import User, UserRole

# 创建测试用的异步 SQLite 内存连接池
# 移除原先的 fixture，现在从 conftest.py 继承

@pytest.mark.asyncio
async def test_create_user(async_db: AsyncSession):
    new_user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashedpassword",
        role=UserRole.admin
    )
    async_db.add(new_user)
    await async_db.commit()
    await async_db.refresh(new_user)

    assert new_user.id is not None
    assert new_user.username == "testuser"
    assert new_user.email == "test@example.com"
    assert new_user.role == UserRole.admin
    assert new_user.status == "active"
