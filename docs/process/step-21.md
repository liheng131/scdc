# Step 21: 执行所需信息

> 关联: [plan.md](../plan.md) | [process.md](../process.md)

## 设计方案

#### Step 21: ...

##### [第1次/最新] 2026-05-17
- **任务目标**: 搭建高可扩展的前端基础工程骨架（基于 Vue 3 + TS + Vite + Pinia + Element Plus），构建标准化的 API 请求封装层及核心页面导航框架（MainLayout），为 MVP 核心页面打下坚实支撑。
- **架构定位**: 位于前端表现层与接口消费基座层 (`frontend/src/api`, `frontend/src/stores`, `frontend/src/components/layout`)。
- **组件分解**:
  - `src/api/client.ts`: 基于 Axios 封装通用 HTTP 客户端，集成请求头 Token 注入与全局响应拦截器（统一错误弹窗提示与 401 跳转）。
  - `src/api/services/*.ts`: 分类封装后端契约（`auth`, `tasks`, `reports`, `templates`, `data_sources` 等接口调用方法）。
  - `src/stores/auth.ts`: Pinia 状态树，管理当前登录用户、JWT 令牌及退出登录逻辑。
  - `src/components/layout/MainLayout.vue`: 标准化后台布局结构，左侧伸缩式菜单导航（数据源、任务、报告、模板、配置等），顶部面包屑与用户信息栏。
- **数据流与控制流**:
  - 用户打开系统或发起操作时，调用 `api/services` 层。
  - 请求被 `client.ts` 拦截，自动附加 `localStorage` 中的 token。
  - 若返回 401 未授权或 403 越权，触发 `authStore.logout()` 并弹出全局提示。
- **接口契约**:
  - 完美映射后端所有 REST 接口响应格式 (`{ code: 0, data: ..., msg: ... }`)。
- **错误处理与边界情况**:
  - 网络断开/超时：全局提示请求超时或网络连接失败。
  - 无权访问：统一拦截跳转至 `/login`。
- **测试策略**:
  - `src/stores/__tests__/auth.spec.ts`: 测试 Pinia store 的状态变更逻辑及 token 存取断言。

## 开发实现

#### Step 21: ...

##### [第1次/最新] 2026-05-17
- **改动范围锚点**:
  - `frontend/src/api/client.ts`: 建立基础 Axios 实例，封装 Token 注入与异常拦截提示 (`ElMessage`)。
  - `frontend/src/api/services/*.ts`: 分层封装 `auth`, `tasks`, `reports`, `templates` 接口服务。
  - `frontend/src/api/index.ts`: 统一对外导出接口。
  - `frontend/src/stores/auth.ts`: 建立 Pinia 用户会话状态树。
  - `frontend/src/components/layout/MainLayout.vue`: 构建现代化响应式左侧导航栏与顶部栏布局。
  - `frontend/src/views/LoginView.vue` 及各个管理骨架页: 构建富交互界面。
  - `frontend/src/router/index.ts`: 配置路由映射与全局前置认证守卫。
  - `frontend/src/stores/__tests__/auth.spec.ts`: 编写会话登录与登出状态变更断言。
- **具体改动**: 
  1. 安装并初始化 Node 依赖模块，打通前后端 API 消费接口规范。
  2. 完成了管理后台主框架的搭建，页面切换与路由权限拦截平滑顺畅，TypeScript 生产编译 0 报错通过。
- **TDD 物理凭证**:
```text
> scdc-frontend@1.0.0 test
> vitest run

 ✓ src/stores/__tests__/auth.spec.ts  (3 tests) 9ms
 ✓ src/components/__tests__/HelloWorld.spec.ts  (1 test) 17ms

 Test Files  2 passed (2)
      Tests  4 passed (4)
   Start at  02:46:31
   Duration  2.46s
```

## 审阅意见

#### Step 21: ...

##### [第1次/最新] 2026-05-17
- **审阅结果**: 通过 (PASS)
- **四大维度验证总结**:
  1. **需求合规性**: 完美搭建了基于 Vue 3 + Vite + Element Plus 的管理控制台骨架，实现精美登录界面与后台伸缩式导航（MainLayout）。
  2. **架构合规性**: 建立了规范化的 HTTP 客户端 (`apiClient`) 及分模块的接口调用层 (`services/*.ts`)，严格统一了全局错误拦截和 Token 存取闭环。
  3. **代码质量**: Pinia 状态库测试用例断言精准，TypeScript 生产构建 (`vue-tsc && vite build`) 零错误通过。
  4. **风险评估**: 拥有完善的 401/403 路由拦截与鉴权守卫，前端安全防线牢固。

## 回滚与验证记录

暂无回滚记录。
