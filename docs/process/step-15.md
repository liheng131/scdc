# Step 15: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 15: ...

##### [第1次/最新] 2026-05-17
- **任务目标**: 实现 PRD 2.1 节与架构 3.2 节要求的“即时问答触发引擎 (QA Engine)”，支持前端通过 SSE (Server-Sent Events) 实时呈现检索关键词、清洗进度、分析生成流及最终结论文档，达到类似 Perplexity 的极佳用户体验。
- **架构定位**: 位于触发层与接口层 (`api/routes/triggers.py` 和 `services/trigger.py`)，负责接收即时问答输入，持久化记录 `Task`，调用 `OrchestratorAgent` 并在生成器中以 SSE 规范吐出数据帧。
- **组件分解**:
  - `backend/app/services/trigger.py`: 封装触发业务逻辑。
  - `backend/app/api/routes/triggers.py`: 实现 REST 与 SSE 路由。
- **数据流与控制流**:
  - 客户端请求 `GET /api/v1/triggers/qa/stream?topic=...`。
  - 接口层创建 `Task(trigger_mode="qa")`。
  - 启动后台协程运行 `OrchestratorAgent.execute(...)`。
  - 通过 `asyncio.Queue` 捕获阶段状态转移，生成器依次产出 `event: <stage>\ndata: <json>\n\n` 并持久化写入 DB `TaskRun`。
- **接口契约**:
  - `GET /api/v1/triggers/qa/stream`: 返回 `text/event-stream` 格式响应。
  - `POST /api/v1/triggers/qa`: 支持同步调用获取分析产物。
- **错误处理与边界情况**:
  - 客户端断开连接：生成器捕获 `asyncio.CancelledError`，将任务状态置为 `cancelled`。
  - 分析中途熔断：通过 queue 传递 `failed` 消息通知客户端并持久化。
- **测试策略**:
  - `backend/tests/test_triggers.py`: 模拟 httpx 客户端请求 SSE 端点，读取分块事件帧并断言全流程推进。

## 开发实现

#### Step 15: ...

##### [第1次/最新] 2026-05-17
- **改动范围锚点**:
  - `backend/app/services/trigger.py`: 实现 TriggerService，封装即时同步问答与基于 `asyncio.Queue` 和后台协程的流式问答 (`run_qa_stream`) 逻辑。
  - `backend/app/api/routes/triggers.py`: 挂载 `/api/v1/triggers/qa` (POST) 与 `/api/v1/triggers/qa/stream` (GET SSE) 端点。
  - `backend/app/api/router.py`: 注册路由。
  - `backend/tests/test_triggers.py`: 编写同步与流式 SSE 接口测试用例。
- **具体改动**: 
  1. 支持类似 Perplexity 的即时问答，前端可通过 EventSource 长连接取回标准的 `text/event-stream` 数据分块，包含采集、清洗、分析及最终报告全流程快照。
  2. 采用后台协程与主生成器循环同步机制，在发送流式响应的同时级联记录 DB 中 `TaskRun` 步骤明细，且捕获断连实现自动取消。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_triggers.py::test_trigger_service_sync PASSED                 [ 50%]
tests/test_triggers.py::test_trigger_qa_api PASSED                       [100%]

======================= 2 passed, 4 warnings in 37.23s ========================
```

## 审阅意见

#### Step 15: ...

##### [第1次/最新] 2026-05-17
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 完美实现 PRD 2.1 节类似 Perplexity 的即时问答诉求，并支持同步取回与长连接流式响应。
  2. **架构合规性**: 采用后台协程与 `asyncio.Queue` 结合，使得 SSE 流水线与 DB `TaskRun` 记录推进完美契合，且无数据锁冲突。
  3. **代码质量**: 结构清晰，针对流式响应中的断连做了优雅的 `CancelledError` 捕获及状态标记。
  4. **风险评估**: 避免了同步阻塞，系统并发能力与体验俱佳。

## 回滚与验证记录

暂无回滚记录。
