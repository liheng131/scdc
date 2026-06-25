"""
CollectorAgent（数据采集 Agent）

职责：
- 使用 LLM 将用户提问扩展为多个低相关性搜索关键词
- 对每个关键词并发搜索，合并去重后取 Top N 条
- 并发爬取目标页面的全文内容
- 爬取失败时降级为使用搜索摘要（snippet）

为什么使用关键词扩展：
- 单一 query 搜索结果有限，多关键词覆盖不同维度
- LLM 生成的关键词彼此相关性低，避免搜索结果重复
- 大幅提升数据覆盖面，接近人工多来源收集效果

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
from sqlalchemy import select
from app.schemas.agent import CollectorInput, CollectedItem, CollectorOutput
from app.services.anysearch import AnySearchService
from app.services.keyword_expander import keyword_expander
from app.services.web_image_extractor import web_image_extractor
from app.crawlers.http_crawler import HTTPCrawler
from app.schemas.crawler import CrawlRequest
from app.core.db import async_session_factory
from app.models.attachment import Attachment

logger = logging.getLogger(__name__)

class CollectorAgent:
    def __init__(self):
        self.search_service = AnySearchService()
        self.crawler = HTTPCrawler()

    async def _load_user_attachments(self, attachment_ids: List[str]) -> List[CollectedItem]:
        """从 attachments 表加载用户上传的附件,转换为 CollectedItem 列表。

        失败(附件不存在/DB 异常)不抛错,只跳过该项,保证不影响主搜索流程。
        """
        if not attachment_ids:
            return []
        items: List[CollectedItem] = []
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Attachment).where(Attachment.id.in_(attachment_ids))
                )
                attachments = result.scalars().all()
                for att in attachments:
                    items.append(
                        CollectedItem(
                            source_type="user_attachment",
                            source_uri=f"attachment://{att.id}",
                            title=att.filename,
                            content=att.parsed_content or "",
                            metadata={
                                "attachment_id": att.id,
                                "file_type": att.file_type,
                                "file_size": att.file_size,
                                **(att.extra_metadata or {}),
                            },
                        )
                    )
        except Exception as e:
            logger.warning("Failed to load user attachments %s: %s", attachment_ids, e)
        return items

    async def execute(self, input_data: CollectorInput) -> CollectorOutput:
        """
        执行采集流程：
        1. LLM 扩展用户提问为多个低相关性搜索关键词
        2. 对每个关键词并发搜索，合并去重后取 Top max_items 条
        3. 并发爬取每个结果的完整页面内容
        4. 爬取失败时降级使用搜索摘要，确保不丢失数据
        5. 加载用户上传的附件,前置到 collected_items 列表
        """
        logger.info(f"CollectorAgent started for task_id: {input_data.task_id}, topic: '{input_data.topic}'")

        # 5. 先加载用户附件（保证附件内容优先于搜索结果,前端可优先展示）
        attachment_items: List[CollectedItem] = await self._load_user_attachments(
            input_data.attachment_ids
        )

        # 1. LLM 关键词扩展
        keywords = await keyword_expander.expand_keywords(input_data.topic)
        logger.info(f"Expanded keywords: {keywords}")
        self._expanded_keywords = keywords  # 缓存供 CollectorOutput 出口使用

        # 2. 对每个关键词并发多类别搜索，合并去重
        async def _search_keyword(keyword: str):
            """对单个关键词执行多类别搜索"""
            try:
                resp = await self.search_service.search_multi_categories(
                    query=keyword,
                    categories=["", "news", "tech"],
                    max_per_category=10,
                    timeout=15,
                )
                if resp.success and resp.results:
                    return resp.results
            except Exception as e:
                logger.warning(f"Search failed for keyword '{keyword}': {e}")
            return []

        search_tasks = [_search_keyword(kw) for kw in keywords]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # 合并所有搜索结果并按 URL 去重
        seen_urls: set = set()
        all_results = []
        for result in search_results:
            if isinstance(result, Exception):
                continue
            for item in result:
                if item.url and item.url not in seen_urls:
                    seen_urls.add(item.url)
                    all_results.append(item)

        # 按 score 降序排序（有 score 的优先），取 Top max_items
        all_results.sort(key=lambda x: x.score or 0, reverse=True)
        top_results = all_results[:input_data.max_items]

        logger.info(f"Total unique results: {len(all_results)}, taking top {len(top_results)}")

        if not top_results:
            logger.warning(f"Search returned empty results for topic '{input_data.topic}'.")
            return CollectorOutput(
                task_id=input_data.task_id,
                success=True,
                items=attachment_items,
                expanded_keywords=self._expanded_keywords,
                warning="no_results",
                metadata={"user_attachment_count": len(attachment_items)},
            )

        collected_items = []

        # 3. 并发爬取 Top 搜索结果
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

        # 附件优先于搜索结果
        collected_items = attachment_items + collected_items

        # 4. 从 Top 5 URL 提取网页截图
        extracted_images = []
        try:
            top_urls = [r.url for r in top_results[:5] if r.url]
            if top_urls:
                extracted_images = await web_image_extractor.extract_chart_screenshots(
                    urls=top_urls,
                    max_images=5,
                    timeout=15000,
                )
        except Exception as e:
            logger.warning(f"Image extraction failed: {e}")

        return CollectorOutput(
            task_id=input_data.task_id,
            success=True,
            items=collected_items,
            expanded_keywords=self._expanded_keywords,
            extracted_images=extracted_images,
            metadata={
                "user_attachment_count": len(attachment_items),
                "keywords_used": keywords,
                "total_search_results": len(all_results),
                "extracted_image_count": len(extracted_images),
            },
        )
