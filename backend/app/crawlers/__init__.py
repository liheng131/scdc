"""
网页爬虫模块

提供多类型网页内容爬取能力：
- BaseCrawler: 爬虫基类，定义核心接口
- HTTPCrawler: HTTP/HTTPS 网页爬取，支持自动清洗和重试
- HTMLCleaner: HTML 内容清洗，提取正文和元数据

设计原则：
- 可扩展性：新爬虫类型只需继承 BaseCrawler 实现 crawl() 方法
- 健壮性：内置超时控制、指数退避重试和优雅降级
- 合规性：支持自定义 User-Agent，降低反爬风控概率
"""
