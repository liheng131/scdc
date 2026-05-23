"""
数据库连接模块

职责：
- 创建异步 PostgreSQL 连接引擎和会话工厂
- 提供 FastAPI 依赖注入用的 get_db 生成器（用于路由中自动管理会话生命周期）
- 连接池配置：pool_size=20 适配单机部署的中等并发量
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# 异步数据库引擎（基于 asyncpg 驱动）
# echo=True 在开发环境打印所有 SQL 语句，生产环境关闭以减少日志噪音
engine = create_async_engine(
    settings.async_postgres_dsn,
    echo=(settings.app_env == "development"),
    pool_size=20,        # 连接池常驻连接数
    max_overflow=10,     # 超出 pool_size 后的最大溢出连接数
    future=True          # 启用 SQLAlchemy 2.0 风格
)

# 异步会话工厂，用于创建独立的数据库会话
# expire_on_commit=False：提交后不使对象过期，允许在事务外继续访问属性
# autoflush=False：手动控制刷新时机，避免隐式刷新带来的副作用
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入用的数据库会话生成器

    用法：在路由函数中声明 `session: AsyncSession = Depends(get_db)`
    每次请求创建一个新会话，请求结束时自动关闭并归还到连接池。
    这样避免了手动管理会话生命周期，同时保证每个请求有独立的数据库上下文。
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
