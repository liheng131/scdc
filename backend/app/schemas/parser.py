"""
文档解析 Schema 模块

定义文件解析（PDF/Word/TXT 等）的数据结构。

ParseResult.chunks 存储分块后的文本列表，用于后续 LLM 上下文处理。
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class Chunk(BaseModel):
    index: int
    content: str
    metadata: Dict[str, Any] = {}

class ParseResult(BaseModel):
    filename: str
    file_type: str
    content: str
    chunks: List[Chunk] = []
    metadata: Dict[str, Any] = {}
