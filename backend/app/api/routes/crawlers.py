"""
网页爬虫 API 路由

提供 HTTP 网页爬取端点，支持 HTML 自动清洗。

用户传入 URL 即可获取清洗后的纯文本内容，
便于人工验证数据源质量或手动提取目标页面信息。
"""

from typing import Any
from fastapi import APIRouter, Depends
from app.api.responses import success_response, ResponseModel
from app.schemas.crawler import CrawlRequest, CrawlResult
from app.crawlers.http_crawler import HTTPCrawler
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()
crawler_service = HTTPCrawler()

@router.post("/crawl", response_model=ResponseModel[CrawlResult])
async def crawl_url(
    request: CrawlRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await crawler_service.crawl(request)
    return success_response(data=result)
