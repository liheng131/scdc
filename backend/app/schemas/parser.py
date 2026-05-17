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
