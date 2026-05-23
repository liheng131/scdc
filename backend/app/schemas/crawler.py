"""
爬虫 Schema 模块

定义 HTTP 爬虫的请求和响应数据结构。

CrawlResult.clean_text 存储经过 HTML 清洗后的纯文本内容，
raw_html 保留原始 HTML 用于调试或降级处理。
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class CrawlRequest(BaseModel):
    url: str
    timeout: int = Field(default=15, ge=1, le=60)
    headers: Optional[Dict[str, str]] = None
    force_clean: bool = True

class CrawlResult(BaseModel):
    url: str
    success: bool
    status_code: Optional[int] = None
    title: Optional[str] = None
    clean_text: Optional[str] = None
    raw_html: Optional[str] = None
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None
