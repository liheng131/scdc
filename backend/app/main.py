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
from app.core.db import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定时任务调度器全局单例，使用数据库会话工厂以便查询和更新任务状态
scheduler = SchedulerService(async_session_factory=async_session_factory)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理器（asynccontextmanager 模式）
    - 启动阶段：启动 Cron 定时任务调度循环，每分钟扫描一次待执行任务
    - 关闭阶段：优雅停止调度循环，避免任务中断
    """
    logger.info("Starting scheduler loop...")
    scheduler.start_loop()
    yield
    logger.info("Stopping scheduler loop...")
    scheduler.stop_loop()

# FastAPI 应用实例，绑定生命周期管理器
app = FastAPI(
    title="SCDC API",
    description="Market Insight AI Agent API",
    version="1.0.0",
    lifespan=lifespan,
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
