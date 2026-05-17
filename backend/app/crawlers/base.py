from abc import ABC, abstractmethod
from app.schemas.crawler import CrawlRequest, CrawlResult

class BaseCrawler(ABC):
    @abstractmethod
    async def crawl(self, request: CrawlRequest) -> CrawlResult:
        """Execute a web crawl and return standard result"""
        pass
