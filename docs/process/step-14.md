# Step 14: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 14: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 构建 M4 任务调度与触发模块的核心底层基石“分析任务管理”，为系统的分析任务 (`Task`) 及其多次运行记录 (`TaskRun`) 提供健壮的 Pydantic 数据契约、异步 CRUD 业务逻辑服务及标准 REST 接口，支持用户手动创建、状态查询、阶段推进与运行快照保存。
- **架构定位**: 位于业务服务层与接口控制层 (`services/task.py` 和 `api/routes/tasks.py`)，直接操作 SQLAlchemy 2.0 异步 Session，并为后续的问答触发引擎和定时调度引擎提供持久化支持。
- **组件分解**:
  - `backend/app/schemas/task.py`: 定义 `TaskCreate`, `TaskUpdate`, `TaskOut`, `TaskRunCreate`, `TaskRunOut` 等完整契约。
  - `backend/app/services/task.py`: 实现 `TaskService` 单例类，封装对 `tasks` 表和 `task_runs` 表的级联创建与阶段更新。
  - `backend/app/api/routes/tasks.py`: 挂载 REST 控制器 `/api/v1/tasks`。
- **数据流与控制流**:
  - `POST /tasks` -> 鉴权 -> `TaskService.create_task` -> 写入数据库 -> 返回 TaskOut。
  - 任务运行记录推进：当主控 Agent 流转状态时，可通过 `TaskService.update_task_run` 记录对应子阶段耗时及中间产物结果。
- **接口契约**:
  - `POST /api/v1/tasks`: 创建新任务。
  - `GET /api/v1/tasks`: 分页列出用户的分析任务列表。
  - `GET /api/v1/tasks/{id}`: 取回指定任务详情及运行记录列表。
  - `DELETE /api/v1/tasks/{id}`: 级联删除任务。
- **错误处理与边界情况**:
  - 任务越权访问：查询或删除时，校验 `created_by == current_user.id`（除 admin 角色外），避免越权。
  - 不存在处理：查询不存在任务时返回 404。
- **测试策略**:
  - `backend/tests/test_tasks.py`: 结合内存测试库，测试任务与运行记录的级联读写及 API 端点行为。

## 开发实现

#### Step 14: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/app/schemas/task.py`: 定义 TaskCreate, TaskUpdate, TaskOut, TaskRunCreate, TaskRunUpdate, TaskRunOut。
  - `backend/app/services/task.py`: 实现 TaskService，提供创建任务、分页查询、更新状态、记录执行步骤 (TaskRun) 的能力，并在返回对象时开启 eager load 解决懒加载报错。
  - `backend/app/api/routes/tasks.py`: 挂载 `/api/v1/tasks` 接口。
  - `backend/app/api/router.py`: 注册路由。
  - `backend/tests/test_tasks.py`: 编写业务逻辑与 API 路由的单元测试。
- **具体改动**: 
  1. 实现了基于 Pydantic 契约的完整任务读写删逻辑，严格控制不同角色访问权限（普通用户只能操作自己的任务，admin 具备全量视角）。
  2. 修复了 SQLAlchemy 异步环境中返回 Pydantic 模型加载关系引发的 `MissingGreenlet` 异常，保证序列化无缝顺畅。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, langsmith-0.4.37, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 2 items

tests/test_tasks.py::test_task_service_crud PASSED                       [ 50%]
tests/test_tasks.py::test_tasks_api PASSED                               [100%]

======================== 2 passed, 4 warnings in 2.96s ========================
```

## 审阅意见

#### Step 14: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 提供了标准化的任务创建、详情查询、状态流转及步骤明细 (TaskRun) 记录，完美满足业务层对任务调度的管理基础。
  2. **架构合规性**: 遵循单机分层架构，服务与 REST 路由职责分明。
  3. **代码质量**: PEP 8 风格与全量 Type Hints 完备，并优雅解决了 SQLAlchemy 异步会话 lazy load 引发的 greenlet 问题。
  4. **风险评估**: 实现了严格的用户数据隔离鉴权，无越权及 SQL 注入漏洞。

## 回滚与验证记录

暂无回滚记录。
