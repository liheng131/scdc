"""
统一 API 响应格式模块

设计目的：
- 前后端约定统一的响应包装器格式 {code: 0, msg: "success", data: ...}
- code=0 表示成功，非 0 表示业务异常（由全局异常处理器赋值）
- 前端拦截器通过 code 值判断请求是否成功，无需检查 HTTP 状态码

为什么用泛型 Generic[T]：
- 允许路由函数声明具体的返回类型，如 ResponseModel[List[DataSourceOut]]
- SWAGGER 文档可以自动生成准确的响应 Schema
"""

from typing import Any, Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")

class ResponseModel(BaseModel, Generic[T]):
    """
    统一响应模型（泛型版本）

    字段说明：
    - code：0 表示成功，非 0 表示业务错误码（对应 HTTP 状态码）
    - msg：成功时为 "success"，失败时为具体错误描述
    - data：成功时返回业务数据，失败时可为 None 或错误详情
    """
    code: int = 0
    msg: str = "success"
    data: Optional[T] = None

def success_response(data: Any = None, msg: str = "success") -> ResponseModel:
    """构造成功响应（code=0）"""
    return ResponseModel(code=0, msg=msg, data=data)

def error_response(code: int, msg: str, data: Any = None) -> ResponseModel:
    """构造错误响应（code 为 HTTP 状态码或自定义业务错误码）"""
    return ResponseModel(code=code, msg=msg, data=data)
