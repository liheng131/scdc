# /plan 登录"没反应"分析（用户已自行修复）

## 排查结论

**后端**：完全正常。
- `POST http://localhost:8000/api/v1/auth/login/access-token` 直接 httpx 调用返回 200 OK，返回 `{code:0, data:{access_token, user}}`
- Admin 用户 `admin / password` 已 seed

**前端架构**：
- 应用**没有独立登录页**（路由表中无 `/login`，`LoginView.vue` 是孤儿文件）
- 登录入口是顶栏右上角"登录/注册"按钮 → 触发 `AuthModal` 模态弹窗
- 模态弹窗内是登录 Tab：用户名/邮箱 + 密码 + 提交

**用户最终反馈**："已修复" + 浏览器状态修正后已可登录。

## 主要嫌疑点（按可能性排序）

1. **CORS 配置缺陷**（潜在）：`allow_origins=["*"]` + `allow_credentials=True` 违反 CORS 规范，浏览器可能拒绝 credentials。但本项目走 Vite 代理（同源），理论上不触发。
2. **`@keyup.enter` 仅绑在密码框**（line 342），其他位置按 Enter 不会提交。
3. **`loginFormRef.validate()` 静默失败**：`if (!loginFormRef.value) return;` 不会提示。
4. **错误吞噬**：`onLoginSubmit` catch 块为空、客户端拦截器只在响应体 `code !== 0` 时 reject。

## 当前状态

无需新增代码改动。用户在 UI 层面自行解决了"模态框未出现"问题。
后续如再次出现类似问题，建议从浏览器 DevTools Network 面板观察 `/api/v1/auth/login/access-token` 是否真有请求发出，并检查 Console 是否有 CORS / TypeError 等提示。
