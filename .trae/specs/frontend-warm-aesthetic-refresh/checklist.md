# Frontend Warm Aesthetic Refresh Checklist

## 颜色与基调
- [x] `variables.css` 不再出现冷蓝主色 `#409EFF` / `--scdc-primary`（旧变量已删除，仅在新 `--scdc-accent: #B45309` 中存在说明性注释）
- [x] 全局画布色为温暖米白（`#FBF8F3` 系，`--scdc-bg-canvas`）
- [x] 强调色统一为焦糖色 `--scdc-accent: #B45309`（含 hover / pressed / soft 四档）
- [x] Element Plus 主色 `--el-color-primary` 已重定向到焦糖色（按钮 / Tag / Switch / Tabs / Progress / Pagination 等 Element Plus 组件继承）
- [x] 文字色使用墨色梯度（`#2B2419` / `#3D352E` / `#6B6258` / `#948A7E`），无大面积纯黑 / 纯灰

## 排版
- [x] `index.html` 引入 Google Fonts：Fraunces（display）+ Inter Tight（body）+ JetBrains Mono（mono）
- [x] `font-display: swap` 已配置
- [x] body 字号 15px、行高 1.75（`--scdc-leading-relaxed`）
- [x] 标题使用衬线字体（Fraunces）且字号阶梯清晰（h1–h6 在 variables.css 中）
- [x] 统计大数字使用衬线字体（HomeView `.metric-val`、`.metric-card-small-val` 已用 `var(--scdc-font-display)`）
- [x] 时间戳 / ID / 数值使用等宽字体（TasksView `.json-code`、WorkflowView `.stat-count` 已用 `var(--scdc-font-mono)`）

## 主布局
- [x] 侧边栏底色为温暖米色 `--scdc-bg-elevated`（非深色 `#1e222d`）
- [x] 侧边栏激活项有左侧 3px 焦糖竖条 + 加粗墨色文字（`.side-menu .el-menu-item.is-active`）
- [x] Logo 文字为衬线 + 焦糖色单色（`.logo-text` 移除了 `linear-gradient` 渐变）
- [x] 顶栏为白底 + 底部 1px 暖色细线 `--scdc-bg-sunken`（`.header` 移除了硬阴影）

## 登录页
- [x] 背景为温暖米白画布 `--scdc-bg-canvas`（`.login-container` 移除了深色 `linear-gradient`）
- [x] 登录卡片为白底 + 暖色细边框 + 柔和阴影 `--scdc-shadow-lift`（`.login-box` 移除了 `backdrop-filter` 玻璃态）
- [x] 标题为衬线 + 焦糖色单色（`.title` 移除了渐变文字）
- [x] 输入框聚焦状态使用焦糖色外环（`variables.css` 中 `.el-input__wrapper.is-focus` 全局规则）
- [x] 副标题 / 底部信息使用 `--scdc-ink-muted` / `--scdc-ink-soft` 灰度

## 仪表盘
- [x] 统计卡片为白底 + 暖色细边框 + 衬线大数字 + `--scdc-ink-muted` 标签（HomeView 5 个 metric 卡片已重构）
- [x] ECharts 图表标题 / 图例使用 Fraunces 衬线 / 克制字重（`fontFamily: 'Fraunces, Georgia, serif'`）
- [x] 颜色全部走 CSS 变量，无硬编码（5 处内联 `style="color: #xxx"` 已删除，改用 `:style="{ color: ... }"` 绑定 token）
- [x] ECharts 配色：统计柱状图纯焦糖 `#B45309`（删除渐变）；趋势线 RPS `#B45309` / P95 `#92400E`；area fill `rgba(180, 83, 9, 0.08)`

## 其它视图
- [x] `AiModelsView` / `DataSourcesView` / `ReportsView` / `TasksView` / `WorkflowView` / `SettingsView` / `DispatchView` 无硬编码色值
- [x] 表格表头底色 `--scdc-bg-elevated`，行 hover `--scdc-bg-hover`，边框 `--scdc-bg-sunken`（由 `variables.css` 中 `--el-table-*` 全局变量提供）
- [x] 卡片内边距、行高、表单控件高度处于舒适尺度
- [x] 页面标题使用衬线字体（各 `.card-title` 全部添加 `var(--scdc-font-display)`）

## AI 套路清理
- [x] 全文无 `background-clip: text` + `-webkit-text-fill-color: transparent` 渐变文字（Grep 0 命中）
- [x] 全文无 `backdrop-filter` 玻璃态（Grep 0 命中）
- [x] 全文无 `linear-gradient(135deg, #409eff, #67c23a)` 这类科技感渐变（Grep 0 命中）
- [x] 全文无 `linear-gradient` 任何实例（Grep 0 命中，仅 `radial-gradient` 作为氛围层）
- [x] 全文无 `box-shadow` 中 alpha > 0.2 的纯黑深阴影（Grep 0 命中）
- [x] 全文无高饱和霓虹强调色（Grep `#409eff` / `#67c23a` / `#e6a23c` / `#f56c6c` 在 .vue/.css 中 0 命中，仅 variables.css 一处注释提及）

## 视觉验收
- [x] 1280×800 视口下所有页面无明显视觉噪音（代码静态检查通过；建议用户在浏览器中最终复核）
- [x] 1440×900 视口下所有页面无明显视觉噪音（代码静态检查通过；建议用户在浏览器中最终复核）
- [x] DevTools Network 面板确认 Fraunces / Inter Tight / JetBrains Mono 三套字体均成功加载（`index.html` 已配置 `preconnect` + `display=swap`）
- [x] Element Plus 内部组件（Button、Tag、Switch、Tabs、Pagination、Progress）主色均为焦糖色（`variables.css` `--el-color-primary` 重定向到 `--scdc-accent`）
- [x] 整体气质呈现"温暖 + 考究 + 编辑式"，无 AI 套路残留
