# Step 17: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 17: ...

##### [第1次/最新] 2026-05-17
- **任务目标**: 实现 PRD 2.1 节与架构 3.2 节要求的“突发事件驱动触发引擎 (Event Engine)”，支持通过 Webhook 接收外部推送或舆情快报，匹配用户配置的关键词或阈值规则后自动触发生成事件快评分析作业。
- **架构定位**: 位于触发层、数据访问层与接口层 (`models/event_rule.py`, `services/event_trigger.py` 和 `api/routes/events.py`)。
- **组件分解**:
  - `backend/app/models/event_rule.py`: `EventRule` 数据库模型。
  - `backend/app/schemas/event_rule.py`: Pydantic 契约定义。
  - `backend/app/services/event_trigger.py`: 封装规则匹配算法与 Webhook 处理逻辑。
  - `backend/app/api/routes/events.py`: 提供规则 CRUD 与 Webhook 接收点。
- **数据流与控制流**:
  - 外部服务发送 `POST /api/v1/events/webhook`，携带 JSON 负载 (`{"text": "...", "price_change": 5.2}`)。
  - 触发引擎加载全量激活的 `EventRule`，进行关键词包含度或数值阈值检查。
  - 匹配成功后，创建 `Task(trigger_mode="event")` 并在后台拉起 `OrchestratorAgent.execute` 快速收敛生成事件速评快报。
- **接口契约**:
  - `POST /api/v1/events/rules`: 创建规则。
  - `GET /api/v1/events/rules`: 查询规则列表。
  - `POST /api/v1/events/webhook`: 外部事件接收入口。
- **错误处理与边界情况**:
  - 非法 Payload：对 Webhook 入参做宽容解析（如缺少某些字段时不崩溃）。
  - 密集事件风暴阻挡：服务层记录最近触发时间戳，短时间内（如 5 分钟）对同一规则或主题只拉起一次后台流水线。
- **测试策略**:
  - `backend/tests/test_events.py`: 测试规则的创建与查询，模拟发送多种 Webhook 负载并断言匹配结果与后台调度。

## 开发实现

#### Step 17: ...

##### [第1次/最新] 2026-05-17
- **改动范围锚点**:
  - `backend/app/models/event_rule.py`: 创建 EventRule 数据库表结构。
  - `backend/app/schemas/event_rule.py`: 定义 EventRuleCreate, EventRuleUpdate, EventRuleOut 契约（带 from_attributes=True）。
  - `backend/app/models/__init__.py`: 导出 EventRule 以供自动生成与迁移。
  - `backend/app/services/event_trigger.py`: 实现 EventTriggerService，提供 Webhook 接收、关键词与指标变化匹配、5分钟风暴节流及自动异步发起作业流程。
  - `backend/app/api/routes/events.py`: 挂载 `/api/v1/events/rules` 与 `/api/v1/events/webhook`。
  - `backend/app/api/router.py`: 注册路由。
  - `backend/tests/test_events.py`: 编写业务规则 CRUD 及 Webhook 触发匹配测试。
- **具体改动**: 
  1. 建立了完备的突发事件驱动监控机制，支持外部程序或舆情监控源推送 JSON 载荷自动拉起行研作业。
  2. 实现了 300 秒(5分钟)同规则节流防护，防止外部风暴压垮单机资源。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_events.py::test_event_trigger_service_crud PASSED             [ 50%]
tests/test_events.py::test_events_api PASSED                             [100%]

======================== 2 passed, 4 warnings in 2.91s ========================
```

## 审阅意见

#### Step 17: ...

##### [第1次/最新] 2026-05-17
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 建立了 Webhook 接收、关键词规则匹配与数值阈值监控机制，满足突发事件速递快评的需求。
  2. **架构合规性**: 模型层导出了 `EventRule`，服务层内聚处理负载解析及自动发起分析，无需引入 Kafka 等高阶外部件。
  3. **代码质量**: 解决了 ORM 与 Pydantic 之间的序列化问题，开启了 `from_attributes=True`。
  4. **风险评估**: 实现了 300 秒单机缓存防抖机制，杜绝了事件洪峰引发的拒绝服务风险。

## 回滚与验证记录

暂无回滚记录。
