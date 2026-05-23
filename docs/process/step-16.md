# Step 16: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 16: ...

##### [第1次/最新] 2026-05-17
- **任务目标**: 实现 PRD 2.1 节与架构 3.2 节要求的“定时调度引擎 (Scheduler Engine)”，支持用户通过 Cron 表达式定义中长期的自动行研监控任务（如每日早晨 8 点生成行业快报）。
- **架构定位**: 位于调度层与接口层 (`services/scheduler.py` 和 `api/routes/schedules.py`)，提供轻量级且高可用的单机异步定时触发器。
- **组件分解**:
  - `backend/app/services/scheduler.py`: 提供 Cron 规则解析、任务生成与后台周期性扫描循环 (`run_scheduler_loop`)。
  - `backend/app/api/routes/schedules.py`: 提供计划任务的 CRUD 及立即触发端点。
- **数据流与控制流**:
  - 用户提交计划任务参数 (`cron: "0 8 * * *"`, `topic`, `max_items`)。
  - 创建 `Task(trigger_mode="schedule", status="scheduled")`。
  - 后台轮询协程每分钟检查当前时间是否匹配 Cron 规则，匹配则发起异步 `OrchestratorAgent.execute` 运行作业。
- **接口契约**:
  - `POST /api/v1/schedules`: 创建定时计划。
  - `GET /api/v1/schedules`: 获取列表。
  - `POST /api/v1/schedules/{id}/trigger`: 立即手动执行一次。
  - `DELETE /api/v1/schedules/{id}`: 删除计划。
- **错误处理与边界情况**:
  - Cron 语法校验：使用正则或分割规则校验输入合法性，防止非法字符串。
  - 重复触发阻拦：确保同一分钟内对同一任务只执行一次。
- **测试策略**:
  - `backend/tests/test_schedules.py`: 校验 Cron 匹配逻辑，测试调度创建、获取及立即触发接口。

## 开发实现

#### Step 16: ...

##### [第1次/最新] 2026-05-17
- **改动范围锚点**:
  - `backend/app/schemas/schedule.py`: 创建 ScheduleCreate, ScheduleOut 契约。
  - `backend/app/services/scheduler.py`: 实现了基于轻量级异步轮询与 Cron 表达式解析算法的 SchedulerService，具备启动/停止常驻扫描循环及单次手动触发 (`trigger_job`) 功能。
  - `backend/app/api/routes/schedules.py`: 挂载 `/api/v1/schedules` 路由。
  - `backend/app/api/router.py`: 注册路由。
  - `backend/tests/test_schedules.py`: 编写多规则 Cron 匹配及 API 接口单元测试。
- **具体改动**: 
  1. 支持对自动行研任务配置类似 `0 8 * * *` 的周期性触发规则，实现 All-in-One 单机高内聚常驻调度。
  2. 提供后台常驻扫描与 REST 手动立即执行双模式，更新及异常处理无缝挂载。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 3 items

tests/test_schedules.py::test_match_cron PASSED                          [ 33%]
tests/test_schedules.py::test_scheduler_service_crud PASSED              [ 66%]
tests/test_schedules.py::test_schedules_api PASSED                       [100%]

======================== 3 passed, 4 warnings in 2.67s ========================
```

## 审阅意见

#### Step 16: ...

##### [第1次/最新] 2026-05-17
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 实现了定期定常监控报告的调度，且完美支持 Cron 语法解析与即刻手动触发测试。
  2. **架构合规性**: 采用单机常驻协程轮询，无需额外部署 Celery Beat 或外部调度器，符合架构轻量化约束。
  3. **代码质量**: 逻辑封装整洁，`match_cron` 覆盖多类复杂通配符表达式，单元测试覆盖全面。
  4. **风险评估**: 捕获轮询异常，不会因单次数据库波动导致整个调度循环死锁。

## 回滚与验证记录

暂无回滚记录。
