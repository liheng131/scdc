# 前端技术栈与架构优化 Spec

## Why
当前前端项目经过审计发现多项布局冲突、性能隐患、安全性不足和视觉设计问题，直接影响用户体验和系统稳定性。核心问题包括：路由与菜单不匹配导致 404、双重 Header 叠加显示、ECharts 内存泄漏、XSS 风险、DispatchView 功能未实现等。

## 前端技术栈总览

| 类别 | 技术 | 版本 |
|------|------|------|
| 框架 | Vue 3 (Composition API + `<script setup>`) | ^3.4.21 |
| 路由 | Vue Router (createWebHistory) | ^4.3.0 |
| 状态管理 | Pinia (Composition API) | ^2.1.7 |
| UI 组件库 | Element Plus | ^2.7.2 |
| HTTP 客户端 | Axios (^1.6.8) + 自定义拦截器 | ^1.6.8 |
| 图表库 | ECharts | ^5.5.0 |
| Markdown | marked | ^18.0.3 |
| 工具库 | @vueuse/core | ^10.9.0 |
| 构建工具 | Vite | ^5.2.6 |
| 语言 | TypeScript (strict mode) | ^5.4.3 |
| 测试 | Vitest + @vue/test-utils | ^1.4.0 |

## What Changes

### 严重问题（必须修复）

1. **路由与菜单不匹配** — MainLayout.vue 侧边栏保留了已删除的"大纲模板"菜单项 (`index="/templates"`)，但路由配置中该路由已不存在。点击会导致导航失败/白屏。

2. **ECharts 内存泄漏** — HomeView.vue 每次数据更新都调用 `echarts.init()` 创建新实例，不销毁旧实例；窗口 resize 时图表不自适应。

3. **XSS 安全风险** — WorkflowView.vue 使用 `v-html` 渲染 marked 解析的 Markdown，未配置 sanitize 选项。

4. **DispatchView 功能缺失** — `handleSave()` 方法空实现，所有配置（cron、邮件、webhook）均为硬编码默认值，不实际保存。

5. **Token 安全性** — Token 通过 localStorage 存储（XSS 易受攻击）；导出报告 URL 将 token 拼接到 query string，可能被浏览器历史记录捕获。

6. **App.vue 与 MainLayout.vue 双重 Header** — App.vue 定义了 `el-header`（蓝色背景），MainLayout 也有自己的 `el-header`（白色背景），视觉上可能叠加。

### 性能问题

7. **Dashboard 指标轮询定时器未清理** — HomeView.vue 使用 `setInterval` 每 10 秒轮询，如果组件被缓存（`<keep-alive>`），定时器仍会运行。

8. **Workflow Store 复杂度** — 对话管理 + SSE 流处理 + localStorage 持久化职责过重，建议将 SSE 流处理抽离为 composable。

9. **无懒加载/虚拟滚动** — 大数据量表格（如 ReportsView、WorkflowView 对话列表）无性能优化。

### 设计与美观问题

10. **无 CSS 变量/主题系统** — 所有颜色硬编码在组件中（`#1e222d`、`#409eff`、`#67c23a`），无统一主题管理。

11. **无响应式设计** — 所有组件无媒体查询，小屏幕设备上布局可能溢出。

12. **无全局 CSS Reset** — 仅重置 `body { margin: 0 }`。

13. **DispatchView 视觉占位** — 页面仅显示"自动化调度与分发通道"占位文本和硬编码配置表单，无实际功能。

## 修改计划

### 阶段一：紧急修复（布局 + 路由）
1. 从 MainLayout.vue 移除"大纲模板"菜单项
2. 检查并修复 App.vue / MainLayout.vue 的 Header 冲突
3. 从 router/index.ts 确认无残留 templates 路由引用

### 阶段二：性能优化
4. 修复 ECharts 实例管理：使用 `chart.dispose()` + resize 监听
5. Dashboard 轮询使用 `onUnmounted` 清理定时器
6. Workflow Store SSE 流处理抽离为 `useWorkflowStream` composable

### 阶段三：安全性增强
7. marked 配置 sanitize（使用 DOMPurify 或 marked 的 sanitize 选项）
8. 导出报告改为后端生成预签名下载 URL，避免 token 暴露在 URL 中
9. Token 安全性评估（短期：添加 token 轮换机制）

### 阶段四：功能补全
10. 实现 DispatchView 的保存功能（对接后端 API）

### 阶段五：设计与美观提升（可选，低优先级）
11. 引入 CSS 变量系统，统一颜色主题
12. 添加基础媒体查询，适配平板/手机端
13. 补充全局 CSS Reset

### 代码清理
14. 删除未使用的 `HelloWorld.vue`
15. 统一 `workflowApi.start()` 使用 `apiClient` 而非 `fetch()`

## Impact
- Affected specs: deprecate-outline-templates（遗留路由清理）
- Affected code:
  - `frontend/src/components/layout/MainLayout.vue`
  - `frontend/src/views/HomeView.vue`
  - `frontend/src/views/WorkflowView.vue`
  - `frontend/src/views/DispatchView.vue`
  - `frontend/src/stores/workflow.ts`
  - `frontend/src/App.vue`
  - `frontend/src/router/index.ts`
  - `frontend/src/components/HelloWorld.vue`

## ADDED Requirements
无

## MODIFIED Requirements

### Requirement: 侧边栏菜单与路由一致性
系统 SHALL 确保 MainLayout.vue 侧边栏中的所有菜单项 `index` 与 Vue Router 路由配置完全匹配，不存在指向无效路由的菜单项。

### Requirement: ECharts 图表实例管理
系统 SHALL 正确管理 ECharts 实例生命周期：初始化时检查是否存在旧实例并销毁；窗口 resize 时调用 `resize()` 自适应；组件卸载时调用 `dispose()` 释放资源。

### Requirement: Markdown 内容安全渲染
系统 SHALL 对 Markdown 渲染结果进行 XSS 过滤，不直接 `v-html` 插入用户可控内容。

### Requirement: 导出报告 URL 安全性
系统 SHALL 不将认证 token 暴露在 URL query string 中。导出报告应使用后端生成预签名下载链接或 Cookie 认证。

## REMOVED Requirements
### Requirement: 大纲模板管理页面
**Reason**: 功能已在 `deprecate-outline-templates` spec 中删除，但侧边栏菜单项未同步清理。
**Migration**: 从 MainLayout.vue 移除对应菜单项。