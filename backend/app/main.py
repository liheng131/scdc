"""
FastAPI 应用入口文件

职责：
1. 创建并配置 FastAPI 应用实例
2. 注册全局中间件（CORS、请求计时）
3. 注册全局异常处理器（业务异常、参数校验异常、兜底异常）
4. 挂载 Prometheus 监控指标端点
5. 管理定时任务调度器（SchedulerService）的生命周期
6. 注册所有 API 路由（/api/v1 前缀）
"""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
from app.core.exceptions import BusinessException
from app.api.responses import error_response
from app.api.middleware import TimingMiddleware
from app.api.router import api_router

from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
from app.services.scheduler import SchedulerService
from app.services.vectorstore import VectorStoreService
from app.services.embedding import EmbeddingService
from app.core.db import async_session_factory, migrate_task_id_column, drop_templates_table, engine
from app.models.base import Base
from app.core.security import get_password_hash

# Import all models so that Base.metadata knows about all tables
from app.models.user import User, UserRole  # noqa: F401
from app.models.report import Report  # noqa: F401
from app.models.task import Task, TaskRun  # noqa: F401
from app.models.workflow_run import WorkflowRun  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定时任务调度器全局单例，使用数据库会话工厂以便查询和更新任务状态
scheduler = SchedulerService(async_session_factory=async_session_factory)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理器（asynccontextmanager 模式）
    - 启动阶段：执行数据库迁移，启动 Cron 定时任务调度循环，每分钟扫描一次待执行任务
    - 关闭阶段：优雅停止调度循环，避免任务中断
    """
    logger.info("Creating database tables if not exists...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.warning("Failed to create database tables: %s", e)

    logger.info("Running database migrations...")
    await migrate_task_id_column()
    await drop_templates_table()

    # 创建默认 admin 用户（如果不存在）
    logger.info("Seeding admin user if not exists...")
    try:
        from sqlalchemy import select
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.username == "admin"))
            existing_admin = result.scalars().first()
            if not existing_admin:
                admin_user = User(
                    username="admin",
                    email="admin@scdc.local",
                    password_hash=get_password_hash("password"),
                    role=UserRole.admin,
                    status="active",
                )
                session.add(admin_user)
                await session.commit()
                logger.info("Admin user created: admin / password")
            else:
                logger.info("Admin user already exists")
    except Exception as e:
        logger.warning("Failed to seed admin user: %s", e)
    logger.info("Initializing AI model configs table...")
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_model_configs (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(100) NOT NULL DEFAULT '',
                    model_name VARCHAR(255) NOT NULL DEFAULT '',
                    model_type VARCHAR(20) NOT NULL DEFAULT 'llm',
                    base_url VARCHAR(500) NOT NULL DEFAULT '',
                    api_key TEXT NOT NULL DEFAULT '',
                    is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ai_model_configs_model_type
                ON ai_model_configs (model_type)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ai_model_configs_is_default
                ON ai_model_configs (is_default)
            """))
            result = await conn.execute(text("SELECT COUNT(*) FROM ai_model_configs"))
            count = result.scalar() or 0
            from app.core.runtime_config import rumtime_config
            rumtime_config._ensure_loaded()
            provider = rumtime_config.get("llm_provider", "")
            base_url = rumtime_config.get("llm_base_url", "")
            api_key = rumtime_config.get("llm_api_key", "")
            model_name = rumtime_config.get("default_model", "")
            embedding_model = rumtime_config.get("embedding_model", "nomic-embed-text")
            from app.core.security import encrypt_api_key
            encrypted_key = encrypt_api_key(api_key)

            # 按类型分别检查并补全，确保三种模型配置都存在
            model_defaults = [
                ("llm", provider, model_name, base_url, encrypted_key),
                ("embedding", "ollama", embedding_model, base_url, ""),
                ("rerank", provider, "bge-reranker-v2-m3", base_url, encrypted_key),
            ]
            for mtype, mprovider, mname, murl, mkey in model_defaults:
                exist = await conn.execute(
                    text("SELECT COUNT(*) FROM ai_model_configs WHERE model_type = :mt AND is_default = TRUE"),
                    {"mt": mtype}
                )
                if (exist.scalar() or 0) == 0:
                    await conn.execute(
                        text("""
                            INSERT INTO ai_model_configs (provider, model_name, model_type, base_url, api_key, is_default, created_at, updated_at)
                            VALUES (:provider, :model_name, :model_type, :base_url, :api_key, TRUE, NOW(), NOW())
                        """),
                        {"provider": mprovider, "model_name": mname, "model_type": mtype,
                         "base_url": murl, "api_key": mkey}
                    )
                    logger.info("Auto-inserted default %s model config: %s / %s @ %s", mtype, mprovider, mname, murl)
    except Exception as e:
        logger.warning("Failed to initialize ai_model_configs: %s", e)
    logger.info("Initializing workflow_runs table...")
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id SERIAL PRIMARY KEY,
                    workflow_id VARCHAR(50) NOT NULL,
                    topic VARCHAR(500) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'idle',
                    current_stage VARCHAR(20) NOT NULL DEFAULT '',
                    stages_json TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_runs_workflow_id
                ON workflow_runs (workflow_id)
            """))
    except Exception as e:
        logger.warning("Failed to initialize workflow_runs: %s", e)

    # Clean up orphan running workflows from previous server restarts
    logger.info("Cleaning up orphan workflows...")
    try:
        from app.services.workflow import workflow_service
        await workflow_service.cleanup_orphan_workflows()
    except Exception as e:
        logger.warning("Failed to cleanup orphan workflows at startup: %s", e)

    logger.info("Initializing vector store...")
    try:
        vectorstore = VectorStoreService()
        try:
            embedding_service = EmbeddingService()
            test_vector = await embedding_service.embed_texts_or_empty(["test"])
            dim = len(test_vector[0]) if test_vector and test_vector[0] else 768
            logger.info("Detected embedding dimension: %d", dim)
        except Exception as e:
            logger.warning("Failed to detect embedding dimension: %s, falling back to 768", e)
            dim = 768
        vectorstore.init_collection(dim=dim)
    except Exception as e:
        logger.warning("Failed to initialize Milvus collection: %s", e)
    logger.info("Starting scheduler loop...")
    scheduler.start_loop()

    # 启动期打印 AnySearch 实际生效的配置（base_url 与 api_key 是否已加载）
    try:
        from app.services.anysearch import AnySearchService
        _probe = AnySearchService()
        logger.info("AnySearch base_url=%r api_key_set=%s", _probe.base_url, bool(_probe.api_key))
    except Exception as e:
        logger.warning("Failed to probe AnySearch config at startup: %s", e)

    yield
    logger.info("Stopping scheduler loop...")
    scheduler.stop_loop()

# FastAPI 应用实例，绑定生命周期管理器
app = FastAPI(
    title="SCDC API",
    description="Market Insight AI Agent API",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # 关闭自动斜杠重定向，避免重定向丢失 Authorization 头
)

# 集成 prometheus_fastapi_instrumentator，自动采集请求量、延迟等指标
Instrumentator().instrument(app).expose(app, endpoint="/api/v1/metrics")

# CORS 跨域中间件：开发阶段允许所有来源，生产环境应限制具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求计时中间件：记录每个请求的处理耗时，便于性能分析
app.add_middleware(TimingMiddleware)

# ===== 全局异常处理器 =====

@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    """
    业务异常统一处理
    将 BusinessException（及其子类 NotFoundException、UnauthorizedException）
    转换为统一的响应格式 {code, msg, data}
    """
    return JSONResponse(
        status_code=exc.code if exc.code >= 400 else 400,
        content=error_response(code=exc.code, msg=exc.message, data=exc.data).model_dump()
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    FastAPI 参数校验异常统一处理
    当请求参数不符合 Pydantic schema 时触发，返回 422 和具体校验错误信息
    """
    return JSONResponse(
        status_code=422,
        content=error_response(code=422, msg="参数校验失败", data=exc.errors()).model_dump()
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    兜底异常处理器：捕获所有未被上层捕获的异常
    防止敏感错误信息泄露到前端，统一返回 500 内部错误
    """
    logger.exception("未捕获的系统异常")
    return JSONResponse(
        status_code=500,
        content=error_response(code=500, msg="服务器内部错误").model_dump()
    )

# 所有业务路由统一挂载到 /api/v1 前缀下
app.include_router(api_router, prefix="/api/v1")
