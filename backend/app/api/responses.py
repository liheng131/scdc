from typing import Any, Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")

class ResponseModel(BaseModel, Generic[T]):
    code: int = 0
    msg: str = "success"
    data: Optional[T] = None

def success_response(data: Any = None, msg: str = "success") -> ResponseModel:
    return ResponseModel(code=0, msg=msg, data=data)

def error_response(code: int, msg: str, data: Any = None) -> ResponseModel:
    return ResponseModel(code=code, msg=msg, data=data)
