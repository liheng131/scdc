# Frontend Topnav & Account Menu Checklist

## 偏好与 i18n
- [x] `vue-i18n@^9` 已安装并写入 `package.json`（`vue-i18n@^9.14.5`）
- [x] `frontend/src/stores/preferences.ts` 存在，含 locale / theme 字段 + localStorage 持久化
- [x] `frontend/src/i18n/zh-CN.ts` 与 `en-US.ts` 存在
- [x] `main.ts` 注册 i18n
- [x] `variables.css` 末尾有 `:root[data-theme="dark"]` Token 块

## 品牌区
- [x] MainLayout 顶栏左上方显示 "U-市场洞察"（衬线焦糖色，主品牌）
- [x] 主品牌下方显示 "洲明科技"（无衬线 muted 色 + letter-spacing 0.18em）
- [x] 顶栏高度 72px，padding 合理
- [x] 整页无侧边栏（el-aside 已删除）

## 顶部水平导航
- [x] 菜单为 `el-menu mode="horizontal"`，包含 4 个菜单项：仪表盘 / 智能体工作流 / 智能报告 / 系统设置
- [x] 激活项底部有 2px 焦糖色下划线
- [x] 路由切换时下划线跟随移动
- [x] 折叠按钮已移除

## 公开首页
- [x] 直接访问 `/` 不重定向到登录页
- [x] 直接访问 `/` 渲染 HomeView 内容
- [x] 路由守卫不再强制重定向

## 登录/注册模态
- [x] 右上角"登录/注册"按钮存在
- [x] 点击按钮弹出居中模态（420px 宽）
- [x] 模态含登录 / 注册两个 Tab
- [x] 登录 Tab 复用 AuthModal 表单，输入有效凭据可登录成功
- [x] 登录成功后模态关闭、右上角变头像
- [x] 注册 Tab 为"请联系管理员"占位，不调用 API
- [x] 模态支持 Esc / 点击遮罩 / 右上角 ✕ 关闭

## 账户菜单
- [x] 头像点击弹出 280px 宽面板
- [x] 面板含 7 个部分：用户信息头 / 外观 / 语言 / 切换账号 / 设置 / 帮助中心 / 退出登录
- [x] 用户信息头含圆形首字母头像（焦糖底 + 焦糖字）+ 用户名（衬线 16px）+ 角色 tag
- [x] 外观行可展开子面板（三选一：系统 / 浅色 / 深色），当前值右侧有 ✓
- [x] 主题切换后整页立即变深/浅色
- [x] 语言行可展开子面板（二选一：中文 / English）
- [x] 语言切换后账户菜单与品牌副标题立即变英文
- [x] 切换账号打开登录模态
- [x] 设置打开修改密码模态
- [x] 帮助中心弹窗显示"帮助文档 / 联系管理员 / 提交工单"
- [x] 退出登录清除 token，右上角恢复"登录/注册"
- [x] 各项之间用暖色细线分隔
- [x] hover 反馈使用 var(--scdc-bg-hover)

## 修改密码模态
- [x] ChangePasswordModal 存在
- [x] 三个字段：当前密码 / 新密码 / 确认新密码
- [x] 校验：新密码 ≥ 8 位且包含字母与数字；两次输入一致
- [x] 提交调用 authApi.changePassword()（无后端时降级提示"功能开发中"）
- [x] 模态视觉与 AuthModal 一致

## 受限页面占位
- [x] WorkflowView 未登录时显示"请登录后使用"占位卡片 + 登录按钮
- [x] SettingsView 同上
- [x] 占位卡片为温暖底色 + 衬线焦糖标题
- [x] 401 拦截器已修复（不再 `window.location.href = '/login'`）

## 暗色主题
- [x] `:root[data-theme="dark"]` 存在
- [x] 暗色底色梯度：#1A1612 画布 / #221D17 表面 / #2D251D 抬升 / #3A3024 下沉
- [x] 暗色墨色梯度：#F0E6D6 strong / #D6C8B0 / #A89880 muted / #7C6E58 soft
- [x] Element Plus 组件在暗色下也正确（按钮 / Tag / Switch / Tabs）
- [x] 强调色焦糖保持不变
- [x] 切换到暗色后整体观感统一（无残留浅色 Token）

## 视觉验收
- [x] 首次访问直接看到首页 + 顶栏
- [x] 顶栏左有品牌、右有登录按钮
- [x] 登录后右上角变头像
- [x] 账户菜单与图 1 视觉一致
- [x] 暗色 / 浅色切换流畅
- [x] 中英文切换流畅
- [x] 退出登录后正确恢复未登录态
- [x] 项目代码中 `window.location.href = '/login'` 全局 0 匹配
- [x] 项目代码中 `requiresAuth` 全局 0 匹配
- [x] 路由表无 `/login` 条目
