# Step 9: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 9: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 构建 M3 智能体流水线首发节点“信息采集 Agent”，负责根据用户查询或任务配置，调度底层的数据源管理、网页爬虫及外部检索服务，将分散的多模态数据归拢为统一规范的原始素材集合。
- **架构定位**: 位于 M3 智能体引擎 `agents/collector.py`，是连接数据采集引擎 (M2) 与数据清洗引擎 (Step 10) 的承上启下枢纽。
- **组件分解**:
  - `backend/app/schemas/agent.py`: 定义 `CollectorInput` (task_id, topic, max_items) 与 `CollectedItem` (source_type, source_uri, title, content, metadata) 及输出 `CollectorOutput`。
  - `backend/app/agents/collector.py`: 实现 `CollectorAgent` 核心执行类。调用外部搜索 `SearXNGService` 并结合 `HTTPCrawler` 抓取前 Top N 条搜索结果详情。
  - `backend/app/api/routes/agents.py`: 暴漏 `/agents/collect` 测试触发接口。
- **数据流与控制流**:
  - 触发采集请求 -> `CollectorAgent.execute` 运行 -> 调用 `SearXNGService.search` 获取网页列表 -> 并发调用 `HTTPCrawler.crawl` 拉取正文 -> 包装为 `CollectedItem` 列表。
- **接口契约**:
  - `POST /api/v1/agents/collect`: 接收 `CollectorInput`，返回 `ResponseModel[CollectorOutput]`。
- **错误处理与降级策略**:
  - 局部抓取失败不中断：对并发执行的单个网页抓取异常进行捕获隔离，仅保留成功的条目；若所有数据源均挂死，则返回带有错误标志的空结果，满足流水线鲁棒性要求。
- **测试策略**:
  - `backend/tests/test_agents.py`: 使用 Mock 服务测试采集 Agent 聚合逻辑与成败隔离表现。

## 开发实现

#### Step 9: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/requirements.txt`: 引入 langchain, langchain-community, langgraph 库支持。
  - `backend/app/schemas/agent.py`: 构建 CollectorInput, CollectedItem, CollectorOutput。
  - `backend/app/agents/collector.py`: 实现 CollectorAgent 核心节点类，组合调用外部搜索与爬虫模块。
  - `backend/app/api/routes/agents.py`: 暴露 `/agents/collect` 触发接口。
  - `backend/app/api/router.py`: 挂载 agents 路由。
  - `backend/tests/test_agents.py`: 编写采集节点 TDD 测试用例。
- **具体改动**: 
  1. 成功构建了 CollectorAgent，利用 asyncio.gather 并发执行 Top N 网页的抓取清洗。
  2. 针对抓取失败的单点节点实现了自动降级（退化为采用 SearXNG 提供的 content snippet），确保了高容错与高可用性。
  3. 通过测试套件全方面校验了采集聚合表现与接口契约包装。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_agents.py::test_collector_agent_execution PASSED              [ 50%]
tests/test_agents.py::test_agents_api PASSED                             [100%]

======================= 2 passed, 2 warnings in 27.76s ========================
```

## 审阅意见

#### Step 9: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 成功串联了 M2 的底层检索与爬取逻辑，提供统一且规范的多源数据抓取清洗接口，符合流水线前置节点规范。
  2. **架构合规性**: 节点逻辑独立于 `agents/collector.py`，输出统一的 `CollectedItem` 数据结构，为下游清洗与分析 Agent 奠定了标准契约。
  3. **代码质量**: PEP8 类型提示完整，通过 `asyncio.gather` 并发极大提升了拉取吞吐量，且对子任务抓取错误做了退化snippet降级，逻辑极其稳健。
  4. **风险评估**: 引入了 `langchain` / `langgraph` 主流框架，无版权风险或高危系统调用漏洞。

## 回滚与验证记录

暂无回滚记录。
