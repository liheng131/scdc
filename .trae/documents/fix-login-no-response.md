# 登录无响应诊断 + 加固计划

## Summary

经过实际探测，后端 / Vite 代理 / 路由均能正常工作（curl 直连 200 耗时 0.45s；通过 `http://localhost:3000/api/...` 代理 200 耗时 0.24s）。登录无响应大概率是**前端运行时问题**：可能是浏览器扩展拦截、stale `localStorage` token 触发 401 死循环、或者 AuthModal 本身的回调链路在某些条件下提前 return。

本计划用**最小侵入**方式完成两件事：
1. 加一个**自动化诊断脚本**（一键检测登录链路各环节）
2. 修复 [client.ts](file:///d:/project/trae_projects/scdc/frontend/src/api/client.ts) 401 处理里一个潜在死循环风险点，并把 axios 默认 timeout 调到更适合后端的值

## Current State Analysis

### 已确认可用
- 后端 `POST /api/v1/auth/login/access-token` 200 响应（curl 实测）
- Vite dev server 监听 `:3000`，`/api` 代理到 `http://localhost:8000` 正常
- CORS `allow_origins=["*"]`，不存在跨域拦截
- 后端日志里没有 login 请求记录 → 浏览器端请求未发出 / 未到达后端

### 关键代码点
- [LoginView.vue](file:///d:/project/trae_projects/scdc/frontend/src/views/LoginView.vue)：旧的整页登录页（router 里**没有** `/login` 路由），**未被使用**
- [AuthModal.vue](file:///d:/project/trae_projects/scdc/frontend/src/components/account/account/AuthModal.vue#L204-L222)：当前唯一的登录入口（在 MainLayout 顶栏的账户菜单里触发）
- [auth.ts store](file:///d:/project/trae_projects/scdc/frontend/src/stores/auth.ts#L35-L46)：login() 调用 `authApi.login({ username, password })`
- [auth.ts service](file:///d:/project/trae_projects/scdc/frontend/src/api/services/auth.ts#L54-L63)：用 `URLSearchParams` 拼 `application/x-www-form-urlencoded`
- [client.ts](file:///d:/project/trae_projects/scdc/frontend/src/api/client.ts#L71-L112)：401 处理逻辑较复杂，存在 stale token 风险

### 关键风险点
**1. /plan 模式下无法写代码，仅能生成计划**

**2. 401 死循环风险（[client.ts L97-L111](file:///d:/project/trae_projects/scdc/frontend/src/api/client.ts#L97-L111)）**
- 已有 token 但后端返回 401 → 当前代码**不**清除 token、**不**登出、**不**重发请求
- 用户卡在"看似登录了但实际 token 无效"的状态，刷新页面才会真正发现问题
- 该 401 还可能因为数据库重启、SESSION 过期、secret_key 变更等场景触发

**3. axios 默认 timeout 30s（[client.ts L33](file:///d:/project/trae_projects/scdc/frontend/src/api/client.ts#L33)）**
- 登录请求如果卡住（代理挂了、后端 hang），用户要等 30s
- 改为 8s 更合理

**4. AuthModal 没有错误兜底提示**
- [AuthModal.vue L217-L218](file:///d:/project/trae_projects/scdc/frontend/src/components/account/AuthModal.vue#L217-L218) `catch (e) {}` 是空块
- 拦截器里 ElMessage 已展示，但若拦截器不触发（比如 `error.response` 为 null 的网络层错误）则完全无反馈
- 修复：捕获到非 null response 的错误时，el-message 兜底一次

**5. 启动时 stale token 静默失败**
- 应用加载时 `isAuthenticated` 取决于 `localStorage.getItem('token')`，但 token 是否真有效未验证
- 第一次请求 401 时才暴露

## Proposed Changes

### 步骤 1：新增一键诊断脚本（最小新增，便于持续诊断）
**文件**：[backend/scripts/diagnose_login.py](file:///d:/project/trae_projects/scdc/backend/scripts/diagnose_login.py)（新建）

- 通过 stdin 接受 `username` / `password`
- 顺序探测：直连后端 (`:8000`)、Vite 代理 (`:3000`)、CORS preflight、登录接口
- 打印每步 `status / time / response snippet`
- 用于以后快速定位"登录没反应"问题

**为什么新增而非修改**：脚本独立运行，不影响运行时；用户下次遇到类似问题可立即复用

### 步骤 2：修复 401 死循环 + 优化超时（client.ts）
**文件**：[frontend/src/api/client.ts](file:///d:/project/trae_projects/scdc/frontend/src/api/client.ts)

**改动 A**：axios `timeout: 30000` → `8000`（仅影响 login 等小请求；大请求可在调用处单独 override）
**改动 B**：401 处理里，**只要是登录相关接口**（路径含 `/auth/login`）的 401，强制清除 token + 跳登录弹窗，避免"半登录"状态
**改动 C**：401 错误时，**始终**给用户一个明确反馈（ElMessage.error），不再依赖 `existingToken` 判断

### 步骤 3：AuthModal 错误兜底（AuthModal.vue）
**文件**：[frontend/src/components/account/AuthModal.vue](file:///d:/project/trae_projects/scdc/frontend/src/components/account/AuthModal.vue)

**改动**：`onLoginSubmit` 的 `catch` 不再为空，至少 `console.error(e)` 记录到控制台 + 在拦截器未触发时显示 fallback 提示
- 不动现有 ElMessage 链路，只补兜底

### 步骤 4：login() 增加 stale token 主动清理
**文件**：[frontend/src/stores/auth.ts](file:///d:/project/trae_projects/scdc/frontend/src/stores/auth.ts)

**改动**：login() 入口检测 `localStorage.getItem('token')` 是否存在，若存在且是登录页路径，先调用一次 `/api/v1/auth/me` 验证，失败则先 logout() 再继续登录流程

## Assumptions & Decisions

- 用户在浏览器访问的是 `http://localhost:3000/`（Vite 端口），而非 `:5173`（已确认无服务）
- 用户登录入口是顶栏"登录"按钮触发的 AuthModal，而非 [LoginView.vue](file:///d:/project/trae_projects/scdc/frontend/src/views/LoginView.vue) 整页
- 后端不需要修改
- 不引入新的依赖

## Verification Steps

1. `python backend/scripts/diagnose_login.py` 能跑通：探测 `:8000` 和 `:3000` 都返回 200
2. 浏览器 console 不再出现未处理异常
3. 清空 localStorage → 顶栏登录 → 看到 `ElMessage.success('登录成功')` + 弹窗关闭 + 顶栏头像出现
4. localStorage 留一个过期的 token → 顶栏登录 → 诊断脚本输出 `401 → cleaned stale token → 重新登录成功`
5. 主动把后端关掉 → 8 秒后看到 `ElMessage.error('网络连接失败或服务器无响应')`（不再等 30s）
6. 输入错误密码 → 看到 `ElMessage.error('Incorrect email or password')` + 表单 loading 状态恢复
