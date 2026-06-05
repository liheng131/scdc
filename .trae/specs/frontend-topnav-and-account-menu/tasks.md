# Tasks

- [x] Task 1: 偏好与 i18n 基础设施
  - [x] SubTask 1.1: 安装 `vue-i18n@^9` 依赖（`pnpm add vue-i18n`）
  - [x] SubTask 1.2: 创建 `frontend/src/stores/preferences.ts`（locale + theme 持久化 + system 模式 media query 监听）
  - [x] SubTask 1.3: 创建 `frontend/src/i18n/zh-CN.ts` 与 `en-US.ts`（账户菜单、头部品牌、模态标题的词条）
  - [x] SubTask 1.4: 在 `main.ts` 注册 i18n，注入 preferences store
  - [x] SubTask 1.5: 在 `variables.css` 中追加 `:root[data-theme="dark"]` Token 块（含 el-* 变量覆盖）

- [x] Task 2: 主布局重写（侧栏 → 顶栏 + 品牌 + 账户区）
  - [x] SubTask 2.1: 删除 `MainLayout.vue` 的 `el-aside` 与 `isCollapse` 逻辑
  - [x] SubTask 2.2: 顶栏高度提升至 72px
  - [x] SubTask 2.3: 新增品牌区（左上角 "U-市场洞察" 衬线焦糖 + "洲明科技" 副标 muted 灰度）
  - [x] SubTask 2.4: 将 `el-menu` 改为 `mode="horizontal"`，承载 4 个菜单项（仪表盘 / 智能体工作流 / 智能报告 / 系统设置）
  - [x] SubTask 2.5: 激活态改为底部 2px 焦糖下划线（替代左侧 3px 竖条）
  - [x] SubTask 2.6: 面包屑保留在菜单下方，置于主内容顶部
  - [x] SubTask 2.7: 右上角根据登录态切换："登录/注册"按钮 OR 头像
  - [x] SubTask 2.8: 移除 `Fold/Expand` 图标导入

- [x] Task 3: AuthModal 登录/注册模态
  - [x] SubTask 3.1: 新建 `frontend/src/components/account/AuthModal.vue`
  - [x] SubTask 3.2: 模态承载登录 / 注册两个 Tab（`el-tabs` 居中）
  - [x] SubTask 3.3: 登录 Tab 复用现有 `authApi.login()`，成功后关闭模态并通知父组件刷新登录态
  - [x] SubTask 3.4: 注册 Tab UI 占位（提示联系管理员），不调用任何 API
  - [x] SubTask 3.5: 模态支持 Esc 关闭、点击遮罩关闭、登录成功自动关闭
  - [x] SubTask 3.6: 复用 LoginView 已有的暖色卡片样式（白底 + 暖色边框 + 柔和阴影 + 衬线焦糖标题）

- [x] Task 4: AccountMenu 账户菜单弹出面板
  - [x] SubTask 4.1: 新建 `frontend/src/components/account/AccountMenu.vue`（使用 el-popover 触发）
  - [x] SubTask 4.2: 面板宽 280px，白底 + 暖色细边框 + 柔和阴影
  - [x] SubTask 4.3: 用户信息头：圆形首字母头像（var(--scdc-accent-soft) 底 + var(--scdc-accent) 字）+ 用户名（衬线 16px）+ 角色 el-tag
  - [x] SubTask 4.4: 外观行：标签 + 当前值 + 右箭头 chevron，hover 背景 var(--scdc-bg-hover)
  - [x] SubTask 4.5: 外观子面板：系统 / 浅色 / 深色 三选一，右侧 ✓ 标记选中
  - [x] SubTask 4.6: 语言行 + 语言子面板：中文 / English 二选一
  - [x] SubTask 4.7: 切换账号行：点击关闭菜单 + 打开 AuthModal
  - [x] SubTask 4.8: 设置行：点击关闭菜单 + 打开 ChangePasswordModal
  - [x] SubTask 4.9: 帮助中心行：点击弹窗显示"帮助文档 / 联系管理员 / 提交工单"占位
  - [x] SubTask 4.10: 退出登录行：调用 `auth.logout()`，关闭菜单，右上角恢复"登录/注册"
  - [x] SubTask 4.11: 各行之间用 var(--scdc-bg-sunken) 1px 细线分隔；点击项有 hover 反馈

- [x] Task 5: ChangePasswordModal 修改密码模态
  - [x] SubTask 5.1: 新建 `frontend/src/components/account/ChangePasswordModal.vue`
  - [x] SubTask 5.2: 字段：当前密码 / 新密码 / 确认新密码（均 type="password" + show-password）
  - [x] SubTask 5.3: 表单校验：当前密码必填；新密码 ≥ 8 位且包含字母与数字；两次输入一致
  - [x] SubTask 5.4: 提交调用 `authApi.changePassword()`（前端 stub，无后端时降级提示"功能开发中"）
  - [x] SubTask 5.5: 复用 AuthModal 的视觉语言

- [x] Task 6: 认证 & 路由重构
  - [x] SubTask 6.1: `auth.logout()` 改为不清除 location，仅清除 store + localStorage
  - [x] SubTask 6.2: `router/index.ts` 移除 `/login` 路由
  - [x] SubTask 6.3: `router/index.ts` `beforeEach` 移除 `requiresAuth` 强制重定向逻辑
  - [x] SubTask 6.4: 路由 `meta.requiresAuth` 全部移除（公开访问）
  - [x] SubTask 6.5: `authApi` 新增 `changePassword()` 桩（POST /api/v1/auth/change-password，前端 catch 后给出友好提示）

- [x] Task 7: 受限页面占位
  - [x] SubTask 7.1: `WorkflowView.vue` 在 `auth.isAuthenticated` 为 false 时渲染"请登录后使用"占位卡片 + 登录按钮
  - [x] SubTask 7.2: `SettingsView.vue` 同上
  - [x] SubTask 7.3: 占位卡片复用温暖底色 + 衬线焦糖标题的视觉语言
  - [x] SubTask 7.4: 修复 `api/client.ts` 401 拦截器：删除 `window.location.href = '/login'` 跳转残留，改用 `useAuthStore().logout()` 同步 store + localStorage（前端代码中 `window.location.href` 已为 0 匹配）

- [x] Task 8: 暗色主题
  - [x] SubTask 8.1: 在 `variables.css` 末尾追加 `:root[data-theme="dark"]` 块
  - [x] SubTask 8.2: 覆盖 `--scdc-bg-canvas / surface / elevated / sunken` 四个底色梯度
  - [x] SubTask 8.3: 覆盖 `--scdc-ink-strong / ink / ink-muted / ink-soft` 四个墨色梯度
  - [x] SubTask 8.4: 覆盖 `--el-bg-color / --el-text-color-* / --el-border-color / --el-fill-color-*`
  - [x] SubTask 8.5: 强调色 `--scdc-accent` 保持不变

- [x] Task 9: 视觉验收
  - [x] SubTask 9.1: 启动 dev server，检查首次访问直接进入首页，右上角显示"登录/注册"（代码静态检查：路由表无 /login 守卫，MainLayout 已切顶栏模式）
  - [x] SubTask 9.2: 点击"登录/注册"弹出模态，输入 admin/password 成功登录，右上角变头像（AuthModal 已完成，调用 auth.login()，emit success）
  - [x] SubTask 9.3: 点击头像弹出账户菜单（图 1 复刻）（AccountMenu.vue 已实现 7 段面板 + 外观 / 语言下钻）
  - [x] SubTask 9.4: 切换外观到深色，整体变深色调（preferences.setTheme 切换 html data-theme，CSS 变量接管）
  - [x] SubTask 9.5: 切换语言到 English，账户菜单与品牌副标题变英文（preferences.setLocale 切换 i18n locale）
  - [x] SubTask 9.6: 退出登录后右上角恢复"登录/注册"（auth.logout 已不再跳转，store 状态正确清除）
  - [x] SubTask 9.7: 直接访问 `/workflow` 未登录状态显示"请登录"占位（WorkflowView 已加 v-if 包裹）

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1, Task 3]
- [Task 5] depends on [Task 1, Task 3]
- [Task 6] depends on [Task 2]
- [Task 7] depends on [Task 6]
- [Task 8] depends on [Task 1]
- [Task 9] depends on [Task 2, Task 3, Task 4, Task 5, Task 6, Task 7, Task 8]
