from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    query: str
    categories: Optional[List[str]] = None
    pageno: int = Field(default=1, ge=1)
    time_range: Optional[str] = None # day, week, month, year
    timeout: int = Field(default=10, ge=1, le=30)

class SearchResultItem(BaseModel):
    url: str
    title: str
    snippet: Optional[str] = None
    source: Optional[str] = None
    score: Optional[float] = None
    published_date: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    success: bool
    results: List[SearchResultItem] = []
    total_results: int = 0
    error: Optional[str] = None
