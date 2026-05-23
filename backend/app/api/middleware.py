"""
API 中间件模块

当前包含：
- TimingMiddleware：请求计时中间件，记录每个请求的方法、路径、状态码和耗时
"""

import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class TimingMiddleware(BaseHTTPMiddleware):
    """
    请求计时中间件

    作用：
    - 在每个 HTTP 响应头中添加 X-Process-Time（秒），前端可按需展示
    - 在日志中记录请求方法、路径、状态码、耗时，用于性能瓶颈分析
    - 继承 BaseHTTPMiddleware 以插入到 FastAPI 请求处理链中
    """
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")
        return response
