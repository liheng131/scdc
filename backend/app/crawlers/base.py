"""
爬虫抽象基类

定义所有爬虫的统一接口 crawl()，确保 CollectorAgent 可以无差别调用不同类型的爬虫。

为什么使用 ABC 抽象基类：
- 强制子类实现 crawl() 方法，避免接口不一致
- 支持 ParserManager 的模式，按类型动态选择爬虫
"""

from abc import ABC, abstractmethod
from app.schemas.crawler import CrawlRequest, CrawlResult

class BaseCrawler(ABC):
    @abstractmethod
    async def crawl(self, request: CrawlRequest) -> CrawlResult:
        """执行网页爬取并返回标准化结果"""
        pass
