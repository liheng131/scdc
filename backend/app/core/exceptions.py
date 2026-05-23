"""
统一业务异常定义

设计目的：
- 避免在路由中到处写 try/except 和 HTTPException
- 通过全局异常处理器（main.py）统一转换为 {code, msg, data} 响应格式
- 子类 NotFoundException / UnauthorizedException 提供语义明确的快速抛出方式

用法：
    raise NotFoundException("数据源不存在")
    raise UnauthorizedException("凭据已过期")
"""

from typing import Any, Optional

class BusinessException(Exception):
    """
    业务异常基类
    所有业务层异常都应继承此类，由全局异常处理器统一捕获
    """
    def __init__(self, message: str, code: int = 400, data: Optional[Any] = None):
        self.message = message
        self.code = code
        self.data = data
        super().__init__(self.message)

class NotFoundException(BusinessException):
    """资源未找到异常（自动映射 HTTP 404）"""
    def __init__(self, message: str = "资源不存在", data: Optional[Any] = None):
        super().__init__(message, code=404, data=data)

class UnauthorizedException(BusinessException):
    """未授权异常（自动映射 HTTP 401）"""
    def __init__(self, message: str = "未授权访问", data: Optional[Any] = None):
        super().__init__(message, code=401, data=data)
