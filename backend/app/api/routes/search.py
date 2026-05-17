from typing import Any
from fastapi import APIRouter, Depends
from app.api.responses import success_response, ResponseModel
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search import SearXNGService
from app.api.deps import get_current_active_user
from app.models.user import User

router = APIRouter()
search_service = SearXNGService()

@router.post("/query", response_model=ResponseModel[SearchResponse])
async def execute_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await search_service.search(request)
    return success_response(data=result)
