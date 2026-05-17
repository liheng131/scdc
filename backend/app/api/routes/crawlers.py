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
