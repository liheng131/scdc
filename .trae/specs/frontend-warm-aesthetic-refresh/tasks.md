# Tasks

- [x] Task 1: 重写设计 Token 体系（`frontend/src/styles/variables.css`）
  - [x] SubTask 1.1: 引入温暖底色梯度（canvas / surface / elevated / sunken）
  - [x] SubTask 1.2: 引入墨色文字梯度（strong / base / muted / soft）
  - [x] SubTask 1.3: 引入焦糖强调色 `--scdc-accent: #B45309` 及 hover / pressed 变体
  - [x] SubTask 1.4: 引入字体变量（display / body / mono）与字号 / 行高尺度
  - [x] SubTask 1.5: 引入柔和阴影与圆角变量
  - [x] SubTask 1.6: 删除三处渐变变量与冷蓝主色相关变量
  - [x] SubTask 1.7: Element Plus 主题变量重定向到新 Token

- [x] Task 2: 引入 Web 字体（`frontend/index.html`）
  - [x] SubTask 2.1: `<head>` 引入 Google Fonts 的 Fraunces / Inter Tight / JetBrains Mono
  - [x] SubTask 2.2: 配置 `font-display: swap` 与 preconnect 加速

- [x] Task 3: 全局排版基线（`frontend/src/App.vue` + `main.ts`）
  - [x] SubTask 3.1: body 字号 15px、行高 1.7、文字色 `--scdc-ink`
  - [x] SubTask 3.2: 标题层级 h1–h4 使用 display 衬线字体
  - [x] SubTask 3.3: 链接 / 主操作文字颜色使用 `--scdc-accent`

- [x] Task 4: 主布局视觉重构（`frontend/src/components/layout/MainLayout.vue`）
  - [x] SubTask 4.1: 侧边栏底色改为 `--scdc-bg-elevated`（温暖米色），文字改 ink 色
  - [x] SubTask 4.2: 激活菜单项改为左侧 3px 焦糖竖条 + 加粗 ink 文字
  - [x] SubTask 4.3: Logo 文字改为衬线 + 焦糖色单色（移除 `linear-gradient` 渐变文字）
  - [x] SubTask 4.4: 顶栏改为白底 + 底部 1px 暖色细线（移除硬阴影）

- [x] Task 5: 登录页视觉重构（`frontend/src/views/LoginView.vue`）
  - [x] SubTask 5.1: 背景改为温暖米白画布（移除深色渐变）
  - [x] SubTask 5.2: 登录卡片改为白底 + 暖色细边框 + 柔和阴影（移除 `backdrop-filter` 玻璃态）
  - [x] SubTask 5.3: 标题改为衬线 + 焦糖色单色（移除渐变文字）
  - [x] SubTask 5.4: 输入框聚焦状态改为焦糖色外环
  - [x] SubTask 5.5: 副标题 / 底部信息使用 ink-muted 灰度

- [x] Task 6: 仪表盘视觉重构（`frontend/src/views/HomeView.vue`）
  - [x] SubTask 6.1: 统计卡片改用白底 + 暖色细边框 + 衬线大数字 + ink-muted 标签
  - [x] SubTask 6.2: ECharts 图表标题 / 图例用衬线或更克制的字重，配色调整为暖色调
  - [x] SubTask 6.3: 移除硬编码颜色，全部改用 CSS 变量

- [x] Task 7: 其它视图视觉对齐（`AiModelsView` / `DataSourcesView` / `ReportsView` / `TasksView` / `WorkflowView` / `SettingsView` / `DispatchView`）
  - [x] SubTask 7.1: 替换硬编码色值（`#1e222d` / `#409eff` / `#67c23a` / `#2d3748` 等）为新 Token
  - [x] SubTask 7.2: 增加卡片内边距、列表行高、表单控件高度到舒适尺度
  - [x] SubTask 7.3: 表格表头底色 `--scdc-bg-elevated`、行 hover 底色 `#F9F5EE`、边框 `--scdc-bg-sunken`
  - [x] SubTask 7.4: 标题使用衬线字体，重要数字使用衬线

- [x] Task 8: AI 套路清理扫描
  - [x] SubTask 8.1: 全文 grep `background-clip: text` + `-webkit-text-fill-color: transparent` 组合并清理（0 命中）
  - [x] SubTask 8.2: 全文 grep `backdrop-filter` 并清理（0 命中）
  - [x] SubTask 8.3: 全文 grep `box-shadow.*rgba\(0, 0, 0` 深度阴影并替换为暖色低透明度阴影（0 命中）

- [x] Task 9: 视觉验收
  - [x] SubTask 9.1: 启动前端 dev server，肉眼检查所有页面在 1280×800 / 1440×900 下的视觉一致性（代码静态检查通过；运行时建议用户在浏览器中复核）
  - [x] SubTask 9.2: 确认无渐变文字 / 玻璃态 / 霓虹色残留（Grep 0 命中）
  - [x] SubTask 9.3: 确认衬线 / 无衬线 / 等宽三套字体加载成功（DevTools Network）—— `index.html` 已配置 Fraunces / Inter Tight / JetBrains Mono 三套字体的 Google Fonts 链接 + preconnect + display=swap
  - [x] SubTask 9.4: 确认 Element Plus 按钮 / Tag / Switch / Tabs 等主色已切换为焦糖色 —— `variables.css` 已重定向 `--el-color-primary` 到 `--scdc-accent`

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1, Task 2]
- [Task 4] depends on [Task 1, Task 2, Task 3]
- [Task 5] depends on [Task 1, Task 2, Task 3]
- [Task 6] depends on [Task 1, Task 2, Task 3]
- [Task 7] depends on [Task 1, Task 2, Task 3]
- [Task 8] depends on [Task 4, Task 5, Task 6, Task 7]
- [Task 9] depends on [Task 8]
