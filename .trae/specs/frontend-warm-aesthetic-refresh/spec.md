# 前端温暖质感视觉刷新 Spec

## Why
当前前端界面（登录页、主布局、卡片、按钮、配色、字体）整体偏冷蓝、视觉语言混杂，普遍使用了 AI 产品常见的设计套路：深色渐变背景、`backdrop-filter` 玻璃态、`linear-gradient` 渐变文字、霓虹强调色。整体气质与一个"市场洞察智能决策系统"应有的"专业、可信、考究"不匹配，且对长时段阅读场景不够友好（对比度过高、行距过紧、字号层级混乱）。

本次刷新专注于视觉语言：建立一套以**温暖底色**为基调、**排版为核心**的设计系统，去除 AI 套路，提升长时间使用的舒适度与审美品质。

## 设计方向

整体气质：**编辑式（Editorial）× 现代极简（Refined Minimalism）**。

- **底色**：以温暖的米白 / 牙白 / 浅咖为主（`#FBF8F3`、`#F4EFE6`、`#EAE3D2` 等），辅以低饱和的暖灰文字（`#3D352E`、`#6B6258`、`#948A7E`）和一抹克制的赭石 / 焦糖强调色（`#B45309` 系），避免冷蓝（`#409EFF`）和霓虹。
- **排版**：引入一款带衬线的展示字体（如 `Fraunces` / `Source Serif 4` / `Noto Serif SC`）作为标题与重要数字，引入一款人文无衬线（如 `Inter Tight` / `Manrope` / `Noto Sans SC`）作为正文。强化字号层级（12 / 13 / 14 / 16 / 20 / 28 / 40）和行高（正文 1.7，标题 1.25），让信息层次一眼可读。
- **空间**：增加卡片内边距、段落间距；列表项与表单元素之间使用 8 的倍数节奏；大量留白替代装饰性分割线。
- **层次**：用极轻的边框（`1px solid #EAE3D2`）、极轻的多层阴影（`0 1px 2px rgba(60,40,20,.04), 0 8px 24px rgba(60,40,20,.06)`）替代生硬分割。
- **禁忌**：禁止使用 `linear-gradient` 文字 / 按钮、禁止使用 `backdrop-filter` 玻璃态、禁止使用任何霓虹色 / 高饱和强调色、禁止在浅色背景上大面积使用纯黑。

## What Changes

### 1. 设计 Token 体系重写（`frontend/src/styles/variables.css`）
- 删除冷蓝主色 `#409EFF`，新增温暖强调色 `--scdc-accent: #B45309`（焦糖 / 琥珀）。
- 重写底色梯度：`--scdc-bg-canvas: #FBF8F3`、`--scdc-bg-surface: #FFFFFF`、`--scdc-bg-elevated: #F4EFE6`、`--scdc-bg-sunken: #EAE3D2`。
- 重写文字色：`--scdc-ink-strong: #2B2419`、`--scdc-ink: #3D352E`、`--scdc-ink-muted: #6B6258`、`--scdc-ink-soft: #948A7E`。
- 删除 `--scdc-gradient-banner`、`--scdc-gradient-logo`、`--scdc-gradient-stat-bar` 三处渐变变量。
- 引入字体变量：`--scdc-font-display`（衬线）、`--scdc-font-body`（人文无衬线）、`--scdc-font-mono`。
- 引入字号尺度 `--scdc-text-xs/sm/base/lg/xl/2xl/3xl/display` 与行高变量。
- 引入语义化间距 `--scdc-radius-card: 14px`、柔和阴影 `--scdc-shadow-soft` / `--scdc-shadow-lift`。

### 2. 引入 Web 字体（`frontend/index.html` + 全局）
- 在 `<head>` 引入 Google Fonts 的 `Fraunces`（display，可变字体）+ `Inter Tight`（body）+ `JetBrains Mono`（code/number）。
- 设置 `font-display: swap`，避免闪烁。

### 3. 全局排版基线
- `body` 字号 15px，行高 1.7，颜色 `--scdc-ink`。
- `h1`–`h4` 使用衬线字体，字号按 display/2xl/xl/lg 阶梯。
- 链接 / 主操作文字颜色使用 `--scdc-accent`，hover 用深一号。

### 4. 主布局重做（`frontend/src/components/layout/MainLayout.vue`）
- 侧边栏从深色（`#1e222d`）改为温暖的浅米底（`#F4EFE6`），文字主色用 `--scdc-ink`，激活项用左侧 3px `--scdc-accent` 竖条 + 加粗文字标识。
- Logo 文字去掉 `linear-gradient` 渐变（`logo-text` 当前存在违规），改为衬线字体 + 焦糖色。
- 顶栏保留白色但增加底部 1px 暖色细线分隔，去掉 `box-shadow`。
- 用户头像 / 角色标签保持现状但用更克制的灰度样式。

### 5. 登录页重做（`frontend/src/views/LoginView.vue`）
- 删除深色渐变背景 `linear-gradient(135deg, #1e222d 0%, #0f1319 100%)`，改为温暖米白画布 + 一处极轻的右上角径向暖光（`radial-gradient(ellipse at top right, #F4EFE6, transparent 60%)`，仅作为氛围）。
- 删除 `backdrop-filter: blur(20px)` 玻璃态（`login-box` 当前违规）。
- 删除标题 `linear-gradient(135deg, #409eff, #67c23a)` 渐变文字，改为衬线 + 焦糖色。
- 卡片背景改为纯白 + 暖色细边框 + 柔和阴影；表单输入框去掉默认蓝边框聚焦，聚焦时改为 1px 焦糖外环。
- 副标题、底部版权信息使用 ink-muted 颜色。

### 6. 全局组件库样式对齐（Element Plus 主题覆盖）
- 主色 `--el-color-primary` 重定向为 `--scdc-accent`。
- 调整 `--el-border-radius-base` 为 10px（更柔和的圆角）。
- 表格 / 卡片 / 按钮 / Tag 等组件通过覆盖样式调整为暖色调：表头底色 `--scdc-bg-elevated`、行 hover 底色 `#F9F5EE`、边框 `--scdc-bg-sunken`。

### 7. 仪表盘 / 列表等关键页面视觉对齐
- `HomeView.vue`：统计卡片改用白底 + 暖色细边框 + 衬线大数字 + ink-muted 标签；图表标题与图例用衬线或更克制的字重。
- 其它视图（`AiModelsView`、`DataSourcesView`、`ReportsView`、`TasksView`、`WorkflowView`、`SettingsView`、`DispatchView`）按统一 Token 替换硬编码色值（如 `#1e222d`、`#409eff`、`#67c23a`、`#2d3748`），并采用更大的内边距与字号阶梯。

### 8. 移除硬编码 AI 套路
- 全文检索 `linear-gradient(.*-text|background-clip: text|text-fill-color: transparent)` 模式，移除全部渐变文字。
- 全文检索 `backdrop-filter`，移除全部玻璃态。
- 全文检索 `box-shadow.*rgba\(0, 0, 0` 中过深的黑阴影（> 0.2 alpha），替换为暖色低透明度阴影。

## Impact
- Affected specs：`frontend-audit-and-optimization`（后续可被本 spec 覆盖；其中 Task 9 引入的 CSS 变量将被替换 / 扩展）
- Affected code：
  - `frontend/src/styles/variables.css`（重写）
  - `frontend/index.html`（引入字体）
  - `frontend/src/App.vue`（基础排版）
  - `frontend/src/components/layout/MainLayout.vue`
  - `frontend/src/views/LoginView.vue`
  - `frontend/src/views/HomeView.vue`
  - `frontend/src/views/AiModelsView.vue`
  - `frontend/src/views/DataSourcesView.vue`
  - `frontend/src/views/ReportsView.vue`
  - `frontend/src/views/TasksView.vue`
  - `frontend/src/views/WorkflowView.vue`
  - `frontend/src/views/SettingsView.vue`
  - `frontend/src/views/DispatchView.vue`

## ADDED Requirements

### Requirement: 温暖底色设计 Token
系统 SHALL 在 `:root` 中定义以暖色为基调的设计 Token 体系：画布色 `#FBF8F3`、表面色 `#FFFFFF`、抬升色 `#F4EFE6`、下沉色 `#EAE3D2`、墨色 `#2B2419` / `#3D352E` / `#6B6258` / `#948A7E`、焦糖强调色 `#B45309`。所有页面与组件 SHALL 通过 CSS 变量引用这些 Token，禁止再使用冷蓝色（`#409EFF`）与霓虹色作为主色或强调色。

#### Scenario: 切换到深色页脚场景
- **WHEN** 任意视图渲染
- **THEN** 背景使用 `--scdc-bg-canvas` 或 `--scdc-bg-surface`，文字使用 `--scdc-ink` 或 `--scdc-ink-muted`，整体观感呈现温暖米白质感

### Requirement: 排版为核心的字体系统
系统 SHALL 通过 `<link>` 引入 Google Fonts 的 `Fraunces`（display，衬线）、`Inter Tight`（body，无衬线）、`JetBrains Mono`（mono），并通过 CSS 变量 `--scdc-font-display` / `--scdc-font-body` / `--scdc-font-mono` 在全局可用。标题、统计数字、品牌名 SHALL 使用 `--scdc-font-display`；正文与表单使用 `--scdc-font-body`；表格中的数值 / 时间戳 / ID 使用 `--scdc-font-mono`。

#### Scenario: 仪表盘统计卡片
- **WHEN** HomeView 渲染统计卡片
- **THEN** 数字使用衬线大字（display 字号阶梯），标签使用 ink-muted 小字

### Requirement: 禁止 AI 套路视觉
系统 SHALL 不得在生产 CSS / 模板中包含：① 文字 / 按钮上的 `linear-gradient` 渐变（`background-clip: text` + `-webkit-text-fill-color: transparent` 组合）；② `backdrop-filter` 玻璃态模糊；③ 高饱和霓虹强调色（饱和度 > 80%、明度 > 60% 且非品牌主色）。代码库 SHALL 通过自动化检索（grep / lint 规则）持续保证这一约束。

#### Scenario: 登录页视觉一致性
- **WHEN** 用户访问 `/login`
- **THEN** 登录卡片为白底 + 暖色细边框 + 柔和阴影；标题为衬线焦糖色单色文字；无模糊玻璃、无渐变文字、无深色科技感背景

### Requirement: 侧边栏与顶栏视觉重构
系统 SHALL 将侧边栏从深色（`#1e222d` 系）改为温暖米色画布，激活态使用左侧 3px 焦糖竖条 + 加粗墨色文字标识。顶栏 SHALL 使用白色背景 + 底部 1px 暖色细线（`--scdc-bg-sunken`）替代硬阴影。

#### Scenario: 路由切换
- **WHEN** 用户在仪表盘 / 工作流 / 报告 / 设置之间切换
- **THEN** 侧边栏对应菜单项出现焦糖竖条 + 加粗 + ink 文字；其它菜单项保持 ink-muted 灰度

## MODIFIED Requirements

### Requirement: 主色（`--el-color-primary`）映射
将 Element Plus 主色从 `--scdc-primary: #409eff`（冷蓝）改为 `--scdc-accent: #B45309`（焦糖）。Element Plus 内部组件（Button、Tag、Switch、Pagination、Progress、Tabs 等）将随之使用焦糖色作为主色。

### Requirement: Logo 文字
Logo 文字（SCDC 洞察智能体）SHALL 使用衬线字体 `Fraunces` + 焦糖色单色（`--scdc-accent`），不再使用 `linear-gradient` 渐变。

### Requirement: 登录页背景与卡片
登录页背景 SHALL 改为温暖米白画布（`--scdc-bg-canvas`），登录卡片 SHALL 为纯白 + 1px 暖色细边框（`--scdc-bg-sunken`） + 柔和阴影（`--scdc-shadow-soft`），不再使用深色渐变 + 玻璃态。

## REMOVED Requirements

### Requirement: 冷蓝主色 `#409EFF` 作为品牌色
**Reason**：冷蓝主色与"温暖、可信、考究"的产品气质不符，且与系统中已有的渐变 / 玻璃态套路绑定，移除后可一并清除相关视觉噪音。
**Migration**：所有引用 `--scdc-primary` / `--scdc-primary-light` / `--scdc-primary-dark` 的地方改用 `--scdc-accent` / `--scdc-accent-hover` / `--scdc-accent-pressed`；Element Plus 主题变量 `--el-color-primary-light-3` / `----el-color-primary-dark-2` 同步重定向。

### Requirement: 三处渐变变量
**Reason**：`--scdc-gradient-banner`、`--scdc-gradient-logo`、`--scdc-gradient-stat-bar` 是 AI 套路的直接产物，违背"禁止渐变文字 / 按钮"原则。
**Migration**：渐变 logo 改为单色衬线；渐变 banner 改为暖色径向氛围（仅装饰背景，不承载文字）；渐变 stat bar 改为纯色条 + 焦糖描边或留白。
