import asyncio
import logging
from typing import List
from app.schemas.agent import CollectorInput, CollectedItem, CollectorOutput
from app.services.search import SearXNGService
from app.crawlers.http_crawler import HTTPCrawler
from app.schemas.search import SearchRequest
from app.schemas.crawler import CrawlRequest

logger = logging.getLogger(__name__)

class CollectorAgent:
    def __init__(self):
        self.search_service = SearXNGService()
        self.crawler = HTTPCrawler()

    async def execute(self, input_data: CollectorInput) -> CollectorOutput:
        logger.info(f"CollectorAgent started for task_id: {input_data.task_id}, topic: '{input_data.topic}'")
        
        # 1. Search for topic
        search_req = SearchRequest(
            query=input_data.topic,
            categories=input_data.search_categories,
            timeout=10
        )
        search_resp = await self.search_service.search(search_req)

        if not search_resp.success or not search_resp.results:
            logger.warning(f"Search failed or returned empty for topic '{input_data.topic}'.")
            return CollectorOutput(
                task_id=input_data.task_id,
                success=True, # Empty but successful degradation
                items=[]
            )

        top_results = search_resp.results[:input_data.max_items]
        collected_items = []

        # 2. Concurrently crawl top results
        async def _crawl_result(item):
            try:
                crawl_req = CrawlRequest(url=item.url, timeout=10, force_clean=True)
                crawl_res = await self.crawler.crawl(crawl_req)
                if crawl_res.success and crawl_res.clean_text:
                    return CollectedItem(
                        source_type="search_crawl",
                        source_uri=item.url,
                        title=crawl_res.title or item.title,
                        content=crawl_res.clean_text,
                        metadata={
                            "published_date": item.published_date,
                            "source": item.source,
                            "score": item.score
                        }
                    )
                elif item.snippet: # Fallback to snippet if crawl failed
                    return CollectedItem(
                        source_type="search_snippet",
                        source_uri=item.url,
                        title=item.title,
                        content=item.snippet,
                        metadata={"source": item.source}
                    )
            except Exception as e:
                logger.warning(f"Failed to crawl {item.url}: {str(e)}")
                if item.snippet:
                    return CollectedItem(
                        source_type="search_snippet",
                        source_uri=item.url,
                        title=item.title,
                        content=item.snippet,
                        metadata={"source": item.source}
                    )
            return None

        crawl_tasks = [_crawl_result(r) for r in top_results]
        results = await asyncio.gather(*crawl_tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, CollectedItem):
                collected_items.append(res)

        return CollectorOutput(
            task_id=input_data.task_id,
            success=True,
            items=collected_items
        )
