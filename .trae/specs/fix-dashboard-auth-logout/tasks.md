# Fix Dashboard Auth Logout - The Implementation Plan (Decomposed and Prioritized Task List)

## [x] Task 1: 修复axios拦截器401处理逻辑，避免静默登出
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修改`frontend/src/api/client.ts`中的401错误处理
  - 在清除token前显示明确的用户提示
  - 确保401处理不会在非预期场景下触发
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: 当API返回401时，axios拦截器应显示"登录凭证已过期或未授权，请重新登录"的错误提示
  - `programmatic` TR-1.2: 401处理后localStorage中的token应被清除
  - `human-judgement` TR-1.3: 用户看到明确的错误提示，而不是静默登出
- **Notes**: 当前实现已经清除token并显示错误消息，但需要确保只在确实需要登出时才执行

## [x] Task 2: 修复应用初始化时的token验证逻辑
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 修改`frontend/src/main.ts`中的应用初始化逻辑
  - 只在localStorage中存在token时才调用`fetchCurrentUser()`
  - 如果`fetchCurrentUser()`失败，清除无效token但不阻断应用启动
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: 当localStorage中没有token时，不应调用`fetchCurrentUser()`
  - `programmatic` TR-2.2: 当`fetchCurrentUser()`返回401时，应清除localStorage中的无效token
  - `human-judgement` TR-2.3: 应用启动时不会因token验证失败而阻断
- **Notes**: 当前实现已添加`fetchCurrentUser()`调用，但需要添加条件判断

## [x] Task 3: 改进HomeView的错误处理，避免单个API失败影响整体
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 修改`frontend/src/views/HomeView.vue`中的错误处理
  - 每个API调用应有独立的错误处理，避免一个失败影响其他
  - metricsApi调用已设置为静默失败，保持此行为
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-3.1: 当`dataSourcesApi.getDataSources()`返回401时，不应清除用户token
  - `programmatic` TR-3.2: 当`tasksApi.getTasks()`返回401时，不应清除用户token
  - `human-judgement` TR-3.3: 用户返回仪表盘时，即使某些API失败也不会被登出
- **Notes**: 需要检查各个API调用的错误处理是否独立

## [x] Task 4: 确保metricsApi.getMetrics()路由不需要认证
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 检查`backend/app/api/routes/metrics.py`中的路由配置
  - 确保`/api/v1/metrics-json/json`不需要认证
  - 如果后端已配置为公开，验证前端调用是否正常
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-4.1: `GET /api/v1/metrics-json/json`不需要认证即可访问
  - `programmatic` TR-4.2: 未登录状态下访问metrics接口应返回200
- **Notes**: 当前metrics路由已不需要认证，但需验证

# Task Dependencies
- Task 2 depends on Task 1
