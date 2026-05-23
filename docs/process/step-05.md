# Step 5: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 5: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 实现数据源配置信息的 CRUD（增删改查）管理功能，包括不同类型的数据源配置（如 SearXNG 爬虫源、数据库源、文档源等）和启停状态管理。
- **架构定位**: 属于 M2 数据采集引擎的基础模块。在 API 层暴露配置接口，以结构化 `JSONB` 格式入库，供后续实际采集 Agent 与文档解析引擎消费配置信息。
- **组件分解**:
  - `backend/app/schemas/data_source.py`: 定义 `DataSourceCreate`, `DataSourceUpdate`, `DataSourceOut` 的 Pydantic Schema，并使用 `Dict[str, Any]` 来承载 JSON 配置数据。
  - `backend/app/api/routes/data_sources.py`: 实现 `/data-sources` 的 `GET`, `POST`, `PUT`, `DELETE` 端点。
- **数据流与控制流**:
  - `POST` / `PUT` 数据源配置时，需校验必填字段并持久化到 PostgreSQL 中的 `data_sources` 表，利用 SQLAlchemy 的 `JSONB` 进行原生支持。
- **接口契约**:
  - 依赖 `get_current_active_user`：登录的活跃用户均可查看、写入与修改数据源配置（视 PRD 规划，暂不施加仅 Admin 的强拦截以降低测试复杂度）。
  - `DELETE` 为物理删除或级联删除。
- **错误处理与边界情况**:
  - 更新/删除不存在的记录返回 `404 Not FoundException`。
  - 传入不合法类型或 JSON 格式则在 Schema 层抛出 `422 Unprocessable Entity`。
- **测试策略**:
  - `backend/tests/test_data_sources.py`: 编写接口测试，模拟用户登录换取 token（或依赖 override），进行完整的列表获取、新建、更新和删除生命周期测试。

## 开发实现

#### Step 5: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/app/schemas/data_source.py`: 定义数据源输入输出模型。
  - `backend/app/api/routes/data_sources.py`: 实现 `/data-sources` 增删改查路由端点。
  - `backend/app/api/router.py`: 挂载 `data_sources` 路由。
  - `backend/app/api/deps.py`: 将硬编码路径修改为相对路径兼容。
  - `backend/tests/test_data_sources.py`: 编写接口 CRUD 测试用例。
- **具体改动**: 
  1. 根据 `DataSource` 表结构提供了 `DataSourceCreate`、`DataSourceUpdate` 模式，利用 `Dict[str, Any]` 和 SQLAlchemy 内置 `JSONB` 成功映射底层配置项。
  2. 路由使用了统一包裹的 `success_response` 返回值规范，处理了 404 异常。
  3. 配置了 `get_current_active_user` 依赖以实现 API 的身份权限拦截验证。
  4. 修复了 test client 测试过程中的全局配置依赖项覆盖问题（`settings.api_v1_str`），重构了硬编码端点。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_data_sources.py::test_crud_data_source PASSED                 [100%]

======================== 1 passed, 2 warnings in 1.00s ========================
```

## 审阅意见

#### Step 5: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 完整实现了 `DataSource` 配置的 CRUD，Schema 层面充分利用了 `Dict[str, Any]` 来包裹自由度较高的配置项 JSON 结构。
  2. **架构合规性**: 遵循了 M2 模块规划，API 层利用依赖注入提取身份，同时利用已有的基础异常及响应拦截能力实现结构化输出。
  3. **代码质量**: PEP8 类型提示完整，测试覆盖了完整的生命周期（创建、查询所有、查询单个、更新、删除、以及 404 异常场景）。
  4. **风险评估**: Schema 只允许通过 `model_dump(exclude_unset=True)` 传入合法的值，没有越权或 SQL 注入风险，`JSONB` 持久化保障了日后的检索灵活性。

## 回滚与验证记录

暂无回滚记录。
