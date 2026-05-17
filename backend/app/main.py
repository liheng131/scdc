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

scheduler = SchedulerService(async_session_factory=async_session_factory)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting scheduler loop...")
    scheduler.start_loop()
    yield
    logger.info("Stopping scheduler loop...")
    scheduler.stop_loop()

app = FastAPI(
    title="SCDC API",
    description="Market Insight AI Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/api/v1/metrics")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Timing
app.add_middleware(TimingMiddleware)

# Exception Handlers
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    return JSONResponse(
        status_code=exc.code if exc.code >= 400 else 400,
        content=error_response(code=exc.code, msg=exc.message, data=exc.data).model_dump()
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_response(code=422, msg="参数校验失败", data=exc.errors()).model_dump()
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("未捕获的系统异常")
    return JSONResponse(
        status_code=500,
        content=error_response(code=500, msg="服务器内部错误").model_dump()
    )

# Routers
app.include_router(api_router, prefix="/api/v1")
