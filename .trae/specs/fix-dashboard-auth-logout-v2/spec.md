# Fix Dashboard Auth Logout V2 Spec

## Why
用户登录并导航到其他页面正常操作后，一旦重新回到仪表盘页面（HomeView）就会登录失效并退出登录。之前的修复（fix-dashboard-auth-logout）已处理了部分问题，但问题仍然存在。需要深入调查根本原因。

## What Changes
- 调查 HomeView 页面触发 401 的根本原因
- 检查 JWT token 的发送和验证流程
- 检查后端 API 对 HomeView 调用的端点的认证逻辑
- 修复导致误触发登出的问题
- 优化 401 处理逻辑，避免误登出

## Impact
- Affected specs: fix-dashboard-auth-logout, auth-register-and-email-login
- Affected code: `frontend/src/api/client.ts`, `frontend/src/views/HomeView.vue`, `frontend/src/stores/auth.ts`, `backend/app/api/routes/`, `backend/app/api/deps.py`

## Investigation Findings

### 当前认证流程
1. 用户登录 → token 存储到 localStorage
2. 应用初始化时，如果 localStorage 有 token，调用 `fetchCurrentUser()` 验证
3. HomeView 挂载时并发调用：`dataSourcesApi.getDataSources()`, `tasksApi.getTasks()`, `reportsApi.getReports()`
4. 这些后端 API 都需要 `get_current_active_user` 认证
5. 如果任何 API 返回 401，axios 拦截器调用 `handle401()` 清除 token 并登出

### 可能的根本原因
1. **Token 未正确发送**：axios 请求拦截器从 localStorage 读取 token，但可能存在时序问题
2. **后端认证问题**：JWT 验证失败（secret_key 不匹配、token 格式问题等）
3. **数据库查询问题**：`get_current_user` 依赖中查询用户失败
4. **并发请求问题**：多个并发请求可能导致后端数据库连接问题
5. **Token 过期问题**：虽然默认 24 小时，但可能存在时区或计算问题

## ADDED Requirements

### Requirement: 401 错误处理应区分真正未认证和临时错误
axios 拦截器在遇到 401 时，应：
1. 先验证 localStorage 中的 token 是否仍然存在
2. 如果 token 存在，可能是后端临时问题，不应立即登出
3. 显示明确错误提示，让用户决定下一步操作

#### Scenario: 返回仪表盘时遇到临时 401
- **WHEN** 用户已登录，导航到其他页面后返回仪表盘
- **THEN** 如果某个 API 返回 401，但 localStorage 中存在有效 token，应显示错误提示而不是立即登出

### Requirement: HomeView API 调用应有独立的错误处理
HomeView 中的每个 API 调用应有独立的错误处理：
1. 单个 API 失败不应影响其他 API
2. 401 错误应被特殊处理，不触发全局登出
3. 用户应能看到哪些数据加载失败

#### Scenario: 单个 API 返回 401
- **WHEN** HomeView 加载时某个 API 返回 401
- **THEN** 该 API 的数据不显示，但其他 API 正常加载，用户不会被登出

## MODIFIED Requirements

### Requirement: JWT Token 验证流程
后端 JWT 验证应确保：
1. Token 格式正确
2. Token 未过期
3. 用户存在于数据库中
4. 用户状态为 active

### Requirement: 前端 Token 管理
前端应确保：
1. Token 正确存储在 localStorage
2. 每次 API 请求都携带正确的 Authorization header
3. Token 刷新或续期机制（如果需要）
