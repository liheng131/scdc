# Fix Dashboard Auth Logout Spec

## Why
用户登录并导航到其他页面后，当返回仪表盘（HomeView）时会自动退出登录。这是因为HomeView在onMounted时并发调用多个需要认证的API（dataSources, tasks, reports等），其中任何一个返回401都会触发axios拦截器的登出逻辑，导致用户被强制退出。

## What Changes
- 修改axios拦截器的401处理逻辑，增加重试或更友好的提示
- 确保`fetchCurrentUser()`只在localStorage中存在有效token时才调用
- 改进HomeView的错误处理，避免因单个API失败导致整体异常
- metricsApi.getMetrics()当前不需要认证，应确保其路由配置正确

## Impact
- Affected specs: auth-register-and-email-login, frontend-topnav-and-account-menu
- Affected code: `frontend/src/api/client.ts`, `frontend/src/main.ts`, `frontend/src/views/HomeView.vue`, `backend/app/api/routes/metrics.py`

## MODIFIED Requirements

### Requirement: Axios 401 Error Handling
axios拦截器在遇到401时，不应立即清除token并登出，而应：
1. 先检查是否有有效的token存储在localStorage中
2. 如果token存在，尝试刷新token或显示"会话已过期，请重新登录"的提示
3. 避免静默清除token导致用户困惑

#### Scenario: 返回仪表盘时遇到401
- **WHEN** 用户已登录，导航到其他页面后返回仪表盘
- **THEN** 如果某个API返回401，应显示明确的错误提示，而不是静默登出用户

### Requirement: Application Initialization Token Validation
应用初始化时验证token的逻辑应更加健壮：
1. 只在localStorage中存在token时才调用`fetchCurrentUser()`
2. 如果`fetchCurrentUser()`失败，清除无效token但不阻断应用启动

#### Scenario: 应用启动时token验证
- **WHEN** 应用启动且localStorage中存在token
- **THEN** 调用`fetchCurrentUser()`验证token有效性
- **WHEN** `fetchCurrentUser()`返回401或其他错误
- **THEN** 清除localStorage中的无效token，应用正常启动显示未登录状态
