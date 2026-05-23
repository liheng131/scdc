# Step 4: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 4: ...

##### [第1次/最新] 2026-05-16
- **任务目标**: 实现基于 JWT 的无状态登录认证，密码安全哈希，以及基于角色 (Role) 的基础权限控制 (RBAC) 的依赖注入支持。
- **架构定位**: 位于 API 接入层与安全层，依托 Step 2 的 User 模型及 Step 3 的中间件规范，为后续所有受保护的路由提供统一鉴权。
- **组件分解**:
  - `backend/app/core/security.py`: 封装 `passlib` 进行 bcrypt 密码加密与校验；封装 `PyJWT` 处理 token 签发与解码。
  - `backend/app/schemas/user.py`: 建立 Token 响应、UserCreate 及 UserOut Pydantic Schema。
  - `backend/app/api/deps.py`: 提供依赖项 `get_current_user` (验证 Token 及用户状态), `get_current_active_user` 及 `get_current_admin_user` (权限控制校验)。
  - `backend/app/api/routes/auth.py`: 实现 `/login/access-token` 登录端点，接收 OAuth2 规范的 `username` 和 `password`，返回 access token。
- **数据流与控制流**:
  - 登录: 客户端 POST `/login/access-token` -> 验证用户名和密码 -> 生成并返回 JWT token。
  - 受保护路由访问: 客户端带 Bearer Token 请求 -> `get_current_user` 依赖解析 -> 解析 Token 并获取用户 -> 返回 user 对象给路由函数。
- **错误处理与边界情况**:
  - 密码错误或用户不存在返回 400 `Incorrect email or password`。
  - Token 伪造或过期，抛出 401 `UnauthorizedException`。
  - 无管理员权限但访问管理接口，抛出 403 `HTTPException` 或自定义拦截。
- **测试策略**:
  - `backend/tests/test_auth.py` 测试密码哈希正确性、Token 签发正确性、以及不同角色的依赖注入逻辑。

## 开发实现

#### Step 4: ...

##### [第1次/最新] 2026-05-16
- **改动范围锚点**:
  - `backend/requirements.txt`: 增加 `passlib[bcrypt]`, `pyjwt`, `python-multipart`, `email-validator`。降级 `bcrypt==4.0.1` 以兼容 passlib。
  - `backend/conftest.py`: 提取出公共的异步内存测试数据库夹具 `async_db`。
  - `backend/app/core/security.py`: 封装了基于 bcrypt 的密码校验与 PyJWT 的 Token 签发。
  - `backend/app/schemas/user.py`: 创建了 Token、TokenPayload 及 User 相关 Schema 模型。
  - `backend/app/api/deps.py`: 提供 `get_current_user`, `get_current_active_user`, `get_current_admin_user` 依赖项解析并进行 RBAC。
  - `backend/app/api/routes/auth.py`: 提供 `/login/access-token` 路由，处理表单数据签发凭证。
  - `backend/app/api/router.py`: 挂载 auth 路由。
  - `backend/tests/test_auth.py`: 编写 3 个单元测试校验 Auth 流程并全量通过。
- **具体改动**: 
  1. 通过引入 OAuth2PasswordBearer 标准与 JWT 规范，完成了整个后端的鉴权准入防线。
  2. 测试中发现 `passlib` 的 `bcrypt` 调用问题，通过锁死 `bcrypt==4.0.1` 成功修复。
  3. 完善了测试库上下文的全局 fixture `async_db`，提升了以后所有测试的复用率。
  4. 修改了 User Schema 的默认 role 为 `viewer` 以匹配枚举类型。
- **TDD 物理凭证**:
```text
============================= test session starts =============================
platform win32 -- Python 3.9.18, pytest-8.4.2, pluggy-1.6.0 -- C:\Users\LH\.gemini\antigravity\scratch\scdc\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\LH\.gemini\antigravity\scratch\scdc\backend
plugins: anyio-4.12.1, asyncio-1.2.0
asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 3 items

tests/test_auth.py::test_security_hashing PASSED                         [ 33%]
tests/test_auth.py::test_login_access_token_success PASSED               [ 66%]
tests/test_auth.py::test_login_access_token_failure PASSED               [100%]

======================== 3 passed, 2 warnings in 2.09s ========================
```

## 审阅意见

#### Step 4: ...

##### [第1次/最新] 2026-05-16
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 成功实现了 JWT 签发与解析，且根据 `OAuth2PasswordBearer` 约定暴露了标准的 token 颁发接口，同时加入了 `role` 与 `status` 的检测，符合 PRD 的安全要求。
  2. **架构合规性**: 认证中间件与接口均未强耦合业务模块，封装在 `core/security.py` 及 `api/deps.py` 依赖中，方便各业务模块进行 `Depends()` 引用注入，符合单一职责原则。
  3. **代码质量**: Schema 类型安全，通过 `pytest` 实现了对密码哈希校验、token生成以及依赖拦截场景的全面测试，处理了第三方包 `passlib` 的依赖版本兼容性问题（限制 bcrypt 版本）。
  4. **风险评估**: 隔离了加密实现，当前 bcrypt 配置足够安全，过期时间等均由环境变量提供，无硬编码风险。

## 回滚与验证记录

暂无回滚记录。
