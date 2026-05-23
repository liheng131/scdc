# Step 7: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 7: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 构建稳定、合规、带自动重试与反爬策略的网页爬取服务，支持针对指定目标网站（新闻、竞品动态、普通网页）进行 HTML 内容抓取、清洗及正文结构化提取。
- **架构定位**: 位于 M2 数据采集与处理引擎的 `crawlers` 模块，为外部 Web 数据源引入提供稳定的拉取通道。
- **组件分解**:
  - `backend/app/schemas/crawler.py`: 定义爬取入参 `CrawlRequest` (URL, headers, timeout) 与输出模型 `CrawlResult` (url, title, raw_html, clean_text, status_code, error)。
  - `backend/app/crawlers/base.py`: 定义基类接口 `BaseCrawler` 与通用请求配置。
  - `backend/app/crawlers/http_crawler.py`: 基于 `httpx.AsyncClient` 结合 `tenacity` 异步重试机制的核心爬虫实现。
  - `backend/app/crawlers/cleaner.py`: 基于 `BeautifulSoup` 的 HTML 清洗提取器（剥离 script/style/nav，提取干净正文与 Meta 信息）。
  - `backend/app/api/routes/crawlers.py`: 暴露 `/crawlers/crawl` 动态抓取测试端点。
- **数据流与控制流**:
  - 客户端请求 `POST /api/v1/crawlers/crawl` -> `HTTPCrawler.fetch` 发起异步 HTTP 请求（带重试与 User-Agent 随机轮换） -> 响应文本送入 `HTMLCleaner.clean` -> 包装返回 `CrawlResult` 结果。
- **接口契约**:
  - `POST /api/v1/crawlers/crawl`: 接收 `CrawlRequest` JSON，返回 `ResponseModel[CrawlResult]`。
- **错误处理与降级策略**:
  - 严格遵循工程纪律，抓取超时或 403/500 等错误时，进行 3 次指数退避重试；若依然失败则记录 Warning 日志，返回带有 `error` 信息的对象，绝不让整个主进程崩溃。
- **测试策略**:
  - `backend/tests/test_crawlers.py`: 使用 `pytest-asyncio` 和 `respx`（或直接访问测试 mock 端点），校验成功抓取、重试逻辑及降级处理表现。

## 开发实现

#### Step 7: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/requirements.txt`: 引入 `beautifulsoup4`, `tenacity` 依赖。
  - `backend/app/schemas/crawler.py`: 定义 CrawlRequest 与 CrawlResult 数据契约。
  - `backend/app/crawlers/`: 实现 BaseCrawler 抽象类、HTMLCleaner 清洗器与 HTTPCrawler 核心采集类。
  - `backend/app/api/routes/crawlers.py`: 提供 `/crawlers/crawl` 动态抓取端点。
  - `backend/app/api/router.py`: 挂载 crawlers 路由模块。
  - `backend/tests/test_crawlers.py`: 编写 HTML 清洗与异常降级重试用例。
- **具体改动**: 
  1. 结合 `tenacity` 的异步重试环 (`@retry`) 实现对 HTTP 拉取异常、超时的 3 次指数退避重试，完美符合降级不崩溃要求。
  2. 采用 `BeautifulSoup` 提取网页正文与 Meta，主动过滤导航栏、脚本等无关噪声，为 RAG 和大模型摘要提供高信噪比输入。
  3. 测试套件成功验证了对异常 URL 的重试后降级行为与清洗组件正确性。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 3 items

tests/test_crawlers.py::test_html_cleaner PASSED                         [ 33%]
tests/test_crawlers.py::test_crawler_degradation PASSED                  [ 66%]
tests/test_crawlers.py::test_crawler_api PASSED                          [100%]

======================= 3 passed, 2 warnings in 13.34s ========================
```

## 审阅意见

#### Step 7: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 完美构建了 Web 抓取能力，且针对 Rule 3 爬虫降级做了精准实现（返回 `success=False` 和 `error`，不崩毁主任务流）。
  2. **架构合规性**: 采用清晰的 `BaseCrawler` 与 `HTMLCleaner` 组件结构，业务与清洗解耦，且自带多 User-Agent 随机切换防反爬机制。
  3. **代码质量**: PEP8 类型安全规范，结合 `tenacity` 的重试处理优雅高效，测试覆盖了正常清洗及错误重试等核心场景。
  4. **风险评估**: 使用 `BeautifulSoup` 和 `httpx`，协议合规，针对 SSL 和重定向做了合理配置，防范了长链接或死链造成的线程卡死风险。

## 回滚与验证记录

暂无回滚记录。
