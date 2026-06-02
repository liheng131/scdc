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

async def migrate_task_id_column() -> None:
    """Migrate reports.task_id from integer to varchar(50) if needed."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'reports' AND column_name = 'task_id'
            """))
            row = result.fetchone()
            if row:
                col_type = row[0]
                if col_type in ('integer', 'bigint', 'int4', 'int8'):
                    logger.info(f"Detected reports.task_id as {col_type}, migrating to varchar(50)...")

                    await conn.execute(text("""
                        ALTER TABLE reports DROP CONSTRAINT IF EXISTS reports_task_id_fkey
                    """))

                    await conn.execute(text("""
                        ALTER TABLE reports
                        ALTER COLUMN task_id TYPE VARCHAR(50)
                        USING task_id::text
                    """))

                    await conn.execute(text("""
                        ALTER TABLE reports
                        ALTER COLUMN task_id DROP DEFAULT
                    """))

                    await conn.execute(text("""
                        ALTER TABLE reports
                        ALTER COLUMN task_id DROP NOT NULL
                    """))

                    logger.info("Successfully migrated reports.task_id to varchar(50)")
                else:
                    logger.info(f"reports.task_id is already {col_type}, no migration needed")
            else:
                logger.info("reports.task_id column not found, skipping migration")
    except Exception:
        logger.exception("Failed to migrate reports.task_id column, continuing...")

async def drop_templates_table() -> None:
    """Drop the unused templates table if it exists."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS templates"))
            logger.info("Dropped templates table (deprecated feature)")
    except Exception:
        logger.exception("Failed to drop templates table, continuing...")
