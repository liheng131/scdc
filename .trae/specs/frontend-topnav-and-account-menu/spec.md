# 前端顶部导航 + 账户菜单重构 Spec

## Why
当前前端采用"左侧深色侧边栏 + 整页登录页"结构，对未登录访客不友好，且缺少现代化的账户中心（语言切换、外观、修改密码等）。需要重塑为：**(1) 顶部水平导航；(2) 首页公开可访问，登录以弹窗形式出现；(3) 右上角账户菜单承载偏好与账户设置**，以匹配"U-市场洞察"作为洲明科技企业级 SaaS 入口的定位。

## What Changes

### 1. 品牌与头部
- 左上角加入品牌区：**"U-市场洞察"**（主品牌，衬线大字）+ 副品牌 **"洲明科技"**（公司名，无衬线小字 / 大写 letter-spacing）。
- 顶部导航栏整体从单行 60px 提升至 **72px**，更舒展、更"工具感"。

### 2. 导航从侧边栏改为顶部
- **删除** `el-aside` 整列侧边栏（240px / 64px 折叠态）。
- **新建** `el-header` 内的水平菜单（`el-menu mode="horizontal"`）：仪表盘 / 智能体工作流 / 智能报告 / 系统设置。
- 选中态用底部 2px 焦糖下划线（替代原本的左侧 3px 竖条，因顶部菜单没有"左侧"概念）。
- 折叠按钮移除（侧边栏已不存在）。

### 3. 认证模型重构
- 路由 `/login` 移除（或保留为深链 `?login=open` 触发模态）。
- 所有路由 `meta.requiresAuth` 改为 `false`，访问不再被强制重定向到登录页。
- 公开访问：Home（`/`）、Reports（`/reports`）。
- 受限访问：Workflow（`/workflow`）、Settings（`/settings`）— 未登录访问时显示"请登录后使用"占位卡片 + 登录按钮（点击打开登录模态）。
- 退出登录后停留在当前页面，不强制跳转（除非当前页本身受限，则展示占位）。

### 4. 登录 / 注册改为模态
- 新建 `frontend/src/components/account/AuthModal.vue`（取代整页 `LoginView.vue`）。
- 模态承载登录 / 注册两个 Tab。**首次未登录访问点击"登录/注册"按钮即弹出。**
- 登录成功后：
  - 关闭模态
  - 右上角"登录/注册"按钮 → 替换为用户头像
  - 触发 `auth.fetchCurrentUser()` 刷新用户信息
  - 若带 `redirect` query 参数，跳转回原页面
- 注册 Tab：因后端目前无 register 接口，**本次仅做 UI 占位**（提示"请联系管理员开通账号"），不调用任何 API。

### 5. 账户菜单（参考图 1）
- 点击右上角头像，弹出 **el-popover** 形式的下拉面板，宽 280px。
- 面板内容（自上而下）：
  1. **用户信息头**：头像（首字母圆形）+ 用户名（衬线 16px）+ 角色标签（"飞书个人用户"）
  2. **外观**：当前值 + 右侧箭头 → 二级面板（系统 / 浅色 / 深色）
  3. **语言**：当前值 + 右侧箭头 → 二级面板（中文 / English）
  4. **切换账号** → 打开登录模态
  5. **设置** → 打开"修改密码"子模态
  6. **帮助中心** → 弹窗显示"帮助文档 / 联系管理员 / 提交工单"占位
  7. **退出登录** → 调用 `auth.logout()`，刷新状态

### 6. 偏好系统（新增）
- 新建 `frontend/src/stores/preferences.ts`（Pinia）：管理 `locale`（'zh-CN' | 'en-US'）和 `theme`（'system' | 'light' | 'dark'），持久化到 localStorage。
- 新建 `frontend/src/i18n/` 目录，引入 `vue-i18n@^9`，提供 `zh-CN.ts` / `en-US.ts` 词条。
- **本次 i18n 仅做"账户菜单 + 头部品牌"的中英对照**，业务页面的内容保持中文（避免过度工程化）。
- 主题系统：
  - 浅色（当前 `variables.css` 现状）
  - 深色：新增 `:root[data-theme="dark"]` 覆盖 Token，背景 `#1A1612` / 表面 `#221D17` / 文字 `#F0E6D6` / 强调保持焦糖
  - 系统：监听 `prefers-color-scheme`，自动切换

### 7. 修改密码模态
- 新建 `frontend/src/components/account/ChangePasswordModal.vue`。
- 字段：当前密码 / 新密码 / 确认新密码。
- 调用后端 `authApi.changePassword()`（**待后端实现**；本次前端预留接口，调用失败时给出友好错误）。
- 若后端未提供接口，前端降级为"联系管理员"提示。

### 8. 保留与废弃
- **保留**：`LoginView.vue` 文件暂时保留，但路由不再指向它；可作为"独立登录页"的兜底。
- **废弃**：`MainLayout.vue` 的 `el-aside` 与 `el-menu` 的侧栏逻辑（保留 `el-header` 区，重新设计）。

## Impact
- Affected specs：`frontend-warm-aesthetic-refresh`（已完成的 token 系统继续复用；不需变更）
- Affected code：
  - `frontend/src/components/layout/MainLayout.vue`（重写：侧栏 → 顶栏 + 品牌区 + 账户区）
  - `frontend/src/views/LoginView.vue`（改为 AuthModal 模式或保留作兜底）
  - `frontend/src/components/account/AuthModal.vue`（新建）
  - `frontend/src/components/account/AccountMenu.vue`（新建）
  - `frontend/src/components/account/ChangePasswordModal.vue`（新建）
  - `frontend/src/stores/preferences.ts`（新建）
  - `frontend/src/stores/auth.ts`（小改：logout 不再硬跳 `/login`）
  - `frontend/src/router/index.ts`（移除 `/login` 路由、移除 `requiresAuth` 守卫）
  - `frontend/src/main.ts`（注册 vue-i18n、引入浅/深主题）
  - `frontend/src/i18n/zh-CN.ts` / `en-US.ts`（新建）
  - `frontend/src/api/services/auth.ts`（增加 `changePassword` 桩）
  - `frontend/src/views/WorkflowView.vue`（顶部加"未登录"占位卡片）
  - `frontend/src/views/SettingsView.vue`（同上）
  - `frontend/src/styles/variables.css`（增加 `:root[data-theme="dark"]` Token 块）

## ADDED Requirements

### Requirement: 品牌区展示
系统 SHALL 在顶部导航最左侧展示品牌区，包含两行：
- 主品牌 "U-市场洞察"，使用 `var(--scdc-font-display)` 衬线 22px / 600 / `var(--scdc-ink-strong)`，其中 "U-" 使用 `var(--scdc-accent)` 焦糖色以与公司名前缀呼应
- 副品牌 "洲明科技"，使用 `var(--scdc-font-body)` 12px / 500 / `var(--scdc-ink-muted)`，letter-spacing 0.18em（西文式呼吸感）

#### Scenario: 首次访问任意页面
- **WHEN** 任意页面渲染
- **THEN** 顶部导航左侧清晰展示 "U-市场洞察" 与 "洲明科技"，主品牌视觉重量明显高于副品牌

### Requirement: 顶部水平导航
系统 SHALL 使用 `el-menu mode="horizontal"` 实现顶部水平导航，包含四个菜单项：仪表盘 / 智能体工作流 / 智能报告 / 系统设置。激活项底部出现 2px `var(--scdc-accent)` 下划线，未激活项为 `var(--scdc-ink-muted)` 文字色，hover 变 `var(--scdc-ink)`。

#### Scenario: 路由切换
- **WHEN** 用户在仪表盘 / 智能体工作流 / 智能报告 / 系统设置之间切换
- **THEN** 顶部对应菜单项出现焦糖下划线 + 墨色文字 + 中粗字重；其它菜单项保持 muted 灰度

### Requirement: 公开首页 + 登录模态
系统 SHALL 允许未登录用户直接访问 `/`（首页）而不重定向。当未登录用户点击右上角"登录/注册"按钮时，弹出 `AuthModal` 模态（居中，宽 420px），承载登录 / 注册 Tab。

#### Scenario: 首次访问站点
- **WHEN** 用户在浏览器地址栏直接访问站点根路径
- **THEN** 直接渲染首页（不显示登录页），右上角显示"登录 / 注册"按钮

#### Scenario: 打开登录模态
- **WHEN** 用户点击右上角"登录 / 注册"按钮
- **THEN** 屏幕中央弹出登录模态，背景半透明遮罩，点击遮罩或按 Esc 可关闭

### Requirement: 登录后右上角变头像
系统 SHALL 在用户成功登录后将右上角"登录/注册"按钮替换为圆形头像（取用户名首字符，背景为 `var(--scdc-accent-soft)`，文字色 `var(--scdc-accent)`），点击头像弹出账户菜单。

#### Scenario: 登录态切换
- **WHEN** 用户在登录模态中输入有效凭据并提交
- **THEN** 模态关闭，右上角"登录 / 注册"按钮消失，被圆形头像替代；账户菜单已可用

### Requirement: 账户菜单（图 1 复刻）
系统 SHALL 提供账户菜单弹出面板，宽 280px，包含：用户信息头（头像 + 用户名 + 角色）+ 外观（当前值 + 箭头 → 子面板：系统/浅色/深色）+ 语言（当前值 + 箭头 → 子面板：中文/English）+ 切换账号 + 设置（修改密码）+ 帮助中心 + 退出登录。子面板以横向滑动或下钻方式展开。

#### Scenario: 点击外观项
- **WHEN** 用户点击账户菜单中的"外观"
- **THEN** 面板右侧展开"系统 / 浅色 / 深色"三选一；当前选中项有右侧 ✓ 标记；点击后立即应用主题并关闭子面板

#### Scenario: 点击语言项
- **WHEN** 用户点击账户菜单中的"语言"
- **THEN** 面板右侧展开"中文 / English"二选一；点击后立即应用并刷新界面文字

#### Scenario: 点击设置项
- **WHEN** 用户点击账户菜单中的"设置"
- **THEN** 弹出"修改密码"模态（当前密码 / 新密码 / 确认新密码），提交后调用 `authApi.changePassword()`，成功后 ElMessage 提示

#### Scenario: 点击切换账号
- **WHEN** 用户点击账户菜单中的"切换账号"
- **THEN** 关闭账户菜单，打开登录模态（保留当前登录态直到新凭据成功）

#### Scenario: 点击退出登录
- **WHEN** 用户点击账户菜单中的"退出登录"
- **THEN** 清除 token 与 user，关闭账户菜单，右上角恢复"登录/注册"按钮；停留在当前页面（若受限页则显示"请登录"占位）

### Requirement: 偏好持久化
系统 SHALL 将 `locale`（zh-CN/en-US）与 `theme`（system/light/dark）持久化到 localStorage，应用初始化时恢复。主题选择"系统"时，监听 `prefers-color-scheme` 媒体查询自动切换。

#### Scenario: 刷新页面保留偏好
- **WHEN** 用户在账户菜单中切换语言为 English 并刷新页面
- **THEN** 应用以英文界面启动（账户菜单、头部品牌副标题等已 i18n 的部分）

### Requirement: 暗色主题 Token
系统 SHALL 在 `variables.css` 中定义 `:root[data-theme="dark"]` 选择器，覆盖：底色梯度（`#1A1612` 画布 / `#221D17` 表面 / `#2D251D` 抬升 / `#3A3024` 下沉）、墨色文字梯度（`#F0E6D6` strong / `#D6C8B0` / `#A89880` muted / `#7C6E58` soft），强调色焦糖保持不变。`el-*` 系列变量同步覆盖。暗色与浅色共用同一组件，CSS 变量自动接管。

#### Scenario: 切换到深色
- **WHEN** 用户在账户菜单 → 外观 → 深色
- **THEN** 整个应用立即切换到深色调（页面背景、卡片表面、表格、文字、边框、阴影均切换），Element Plus 组件（按钮、Tag、Switch、Tabs 等）也切换

## MODIFIED Requirements

### Requirement: 路由守卫
**移除**原本 `beforeEach` 中"未登录强制重定向到 `/login`"的逻辑。所有路由 `meta.requiresAuth` 设为 `false` 或省略。受限页面（Workflow / Settings）由组件自身根据 `auth.isAuthenticated` 渲染占位。

### Requirement: 退出登录
**修改** `auth.logout()`：不再 `window.location.href = '/login'`，仅清除 localStorage 与 store 状态。

### Requirement: 路由表
**移除** `/login` 路由（保留 LoginView.vue 文件作历史记录）。

## REMOVED Requirements

### Requirement: 整页登录页
**Reason**：登录改为模态式，整页登录页与"直接进入首页"的需求冲突。
**Migration**：原 LoginView.vue 文件保留但路由不再引用；可作为独立登录页的兜底深链。

### Requirement: 侧边栏折叠态
**Reason**：导航从侧栏改为顶栏后，折叠态无意义。
**Migration**：MainLayout.vue 移除 `isCollapse` 状态、`toggleCollapse` 方法与 `Fold/Expand` 图标导入。
