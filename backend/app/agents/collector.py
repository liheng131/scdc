"""
CollectorAgent（数据采集 Agent）

职责：
- 使用 AnySearch 搜索引擎搜索指定主题
- 对搜索结果并发爬取目标页面的全文内容
- 爬取失败时降级为使用搜索摘要（snippet）

为什么使用 AnySearch：
- 商业搜索 API，结果稳定可预期
- 覆盖度足以支撑一般市场洞察场景
- 通过 API Key 鉴权，避免被反爬拦截

为什么并发爬取：
- 网络 IO 密集，asyncio.gather 可大幅缩短总采集时间
- 单个页面超时不会阻塞其他页面的爬取
"""

import asyncio
import logging
from typing import List
from app.schemas.agent import CollectorInput, CollectedItem, CollectorOutput
from app.services.anysearch import AnySearchService
from app.crawlers.http_crawler import HTTPCrawler
from app.schemas.search import SearchRequest
from app.schemas.crawler import CrawlRequest

logger = logging.getLogger(__name__)

class CollectorAgent:
    def __init__(self):
        self.search_service = AnySearchService()
        self.crawler = HTTPCrawler()

    async def execute(self, input_data: CollectorInput) -> CollectorOutput:
        """
        执行采集流程：
        1. 调用 SerpAPI 搜索主题关键词，获取前 max_items 条结果
        2. 并发爬取每个结果的完整页面内容
        3. 爬取失败时降级使用搜索摘要，确保不丢失数据
        """
        logger.info(f"CollectorAgent started for task_id: {input_data.task_id}, topic: '{input_data.topic}'")

        # 1. 搜索主题
        search_req = SearchRequest(
            query=input_data.topic,
            timeout=10
        )
        search_resp = await self.search_service.search(search_req)

        if not search_resp.success:
            logger.warning(f"AnySearch search failed for topic '{input_data.topic}': {search_resp.error}")
            return CollectorOutput(
                task_id=input_data.task_id,
                success=False,
                error=f"AnySearch search failed: {search_resp.error}"
            )

        if not search_resp.results:
            logger.warning(f"Search returned empty results for topic '{input_data.topic}'.")
            return CollectorOutput(
                task_id=input_data.task_id,
                success=True,
                items=[],
                warning="no_results"
            )

        top_results = search_resp.results[:input_data.max_items]
        collected_items = []

        # 2. 并发爬取 Top 搜索结果
        async def _crawl_result(item):
            """爬取单个搜索结果的目标页面"""
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
                elif item.snippet:  # 爬取失败→降级使用搜索摘要
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

        # asyncio.gather 并发执行所有爬取任务，最大化效率
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
