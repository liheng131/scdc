from typing import Any, Optional

class BusinessException(Exception):
    def __init__(self, message: str, code: int = 400, data: Optional[Any] = None):
        self.message = message
        self.code = code
        self.data = data
        super().__init__(self.message)

class NotFoundException(BusinessException):
    def __init__(self, message: str = "资源不存在", data: Optional[Any] = None):
        super().__init__(message, code=404, data=data)

class UnauthorizedException(BusinessException):
    def __init__(self, message: str = "未授权访问", data: Optional[Any] = None):
        super().__init__(message, code=401, data=data)
