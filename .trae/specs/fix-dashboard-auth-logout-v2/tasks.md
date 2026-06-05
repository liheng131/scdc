# Fix Dashboard Auth Logout V2 - The Implementation Plan

## 问题根本原因分析

经过深入代码审查，问题的根本原因如下：

1. **HomeView 在每次挂载时都会调用需要认证的 API**：
   - `fetchSummaryData()` 在 `onMounted` 中并发调用 `dataSourcesApi.getDataSources()`, `tasksApi.getTasks()`, `reportsApi.getReports()`
   - 这些 API 都需要后端 JWT 认证（`get_current_active_user`）

2. **axios 401 拦截器会清除 token 并登出**：
   - 当任何 API 返回 401 时，`handle401()` 会被调用
   - `handle401()` 清除 localStorage 中的 token 和用户信息
   - 调用 `authStore.logout()` 清除 Pinia store
   - 这导致用户被强制登出

3. **可能导致 401 的场景**：
   - JWT token 过期（默认 24 小时）
   - 后端数据库连接问题导致 `get_current_user` 查询失败
   - 并发请求导致后端数据库会话问题
   - 其他页面操作意外清除了 token

4. **当前 401 处理的问题**：
   - 一旦遇到 401 就立即登出，没有区分真正未认证和临时错误
   - 没有给用户任何挽回机会
   - 没有检查 localStorage 中是否仍存在有效 token

## [x] Task 1: 优化 axios 401 拦截器，避免误登出
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修改 `frontend/src/api/client.ts` 中的 `handle401()` 函数
  - 在清除 token 前，先检查 localStorage 中是否仍存在 token
  - 如果 token 存在，显示错误提示但不立即清除 token
  - 添加"确认登出"的用户交互，让用户决定是否重新登录
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: 当 API 返回 401 时，axios 拦截器应检查 localStorage 中是否仍存在 token
  - `programmatic` TR-1.2: 如果 token 存在，应显示明确的错误提示而不是立即登出
  - `human-judgement` TR-1.3: 用户应有机会决定是否重新登录，而不是被强制登出

## [x] Task 2: 改进 HomeView 错误处理
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修改 `frontend/src/views/HomeView.vue` 中的 `fetchSummaryData()` 函数
  - 为每个 API 调用添加独立的错误处理
  - 401 错误应被特殊处理，不触发全局登出
  - 用户应能看到哪些数据加载失败，但不会被登出
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: 当 `dataSourcesApi.getDataSources()` 返回 401 时，不应触发全局登出
  - `programmatic` TR-2.2: 当 `tasksApi.getTasks()` 返回 401 时，不应触发全局登出
  - `human-judgement` TR-2.3: 用户返回仪表盘时，即使某些 API 失败也不会被登出

## [x] Task 3: 添加 401 错误详细日志
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 在 axios 拦截器和 HomeView 中添加详细的错误日志
  - 记录 401 错误发生时的请求 URL、响应状态、错误详情
  - 帮助后续问题排查
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: 401 错误发生时应记录请求 URL 和响应详情到控制台
  - `human-judgement` TR-3.2: 开发者应能通过控制台日志快速定位 401 原因

## [x] Task 4: 调查后端认证问题（如果需要）
- **Priority**: P1
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 如果前端优化后问题仍然存在，需要调查后端认证问题
  - 检查 JWT token 验证逻辑
  - 检查数据库连接和查询是否正常
  - 检查并发请求是否导致数据库会话问题
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: 后端 API 应正确验证 JWT token
  - `programmatic` TR-4.2: 数据库查询应正常返回用户信息
  - `human-judgement` TR-4.3: 并发请求不应导致认证失败

# Task Dependencies
- Task 4 depends on Task 1 and Task 2
