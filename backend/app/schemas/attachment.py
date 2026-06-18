"""
附件 Schema 模块

定义附件创建、查询、响应的 Pydantic 数据结构。

AttachmentOut 暴露给前端的字段：
- parsed_content: 解析后的纯文本内容
- parsed_chunks: 分块后的列表（每块包含 index + content + metadata）
- metadata: 来自解析器的额外信息（如图片尺寸、OCR 引擎等）
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

class AttachmentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    file_hash: str
    parsed_content: Optional[str] = None
    parsed_chunks: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
