# Frontend Audit & Optimization Checklist

## Task 1: 路由与菜单一致性
- [x] MainLayout.vue 已移除"大纲模板"菜单项及对应图标导入
- [x] App.vue 已移除与 MainLayout 冲突的多余 el-header
- [x] router/index.ts 无残留的 templates 路由配置（仅有注释提及，无实际路由定义）

## Task 2: ECharts 实例生命周期管理
- [x] HomeView.vue 使用实例变量跟踪 ECharts 实例
- [x] 图表初始化前调用 dispose() 销毁旧实例
- [x] 添加 window resize 监听并调用 chart.resize()
- [x] onUnmounted 钩子中正确清理所有 ECharts 实例

## Task 3: Dashboard 轮询定时器清理
- [x] HomeView.vue 的 setInterval 在 onUnmounted 中被清理（metricsTimer）

## Task 4: Markdown XSS 防护
- [x] dompurify 已安装并引入
- [x] workflow.ts 中使用 DOMPurify.sanitize() 过滤 marked 输出
- [x] 两处使用点均已覆盖（completed 事件 + loadHistoryFromServer）

## Task 5: Workflow Store SSE 流处理抽离
- [x] useWorkflowStream composable 已创建
- [ ] workflow.ts 使用 composable 而非直接处理 SSE 逻辑（进行中：store 仍内联处理）

## Task 6: 导出报告 URL 安全性
- [x] exportReportUrl 不再包含 token 参数
- [x] getExportHeaders 提供 Authorization header
- [x] 导出功能使用 header 认证

## Task 7: DispatchView 功能补全
- [x] DispatchView handleSave() 实现完整保存逻辑
- [x] onMounted 时从后端加载现有配置
- [x] 后端 /dispatch-config 端点已实现
- [x] 前端 API 方法 getDispatchConfig / saveDispatchConfig 已实现

## Task 8: 代码清理
- [x] HelloWorld.vue 已删除
- [ ] workflowApi 统一使用 apiClient（进行中：reentryStream 仍使用原生 fetch()）

## Task 9: 设计优化
- [x] CSS 变量系统已引入（variables.css）
- [x] 基础媒体查询已添加
- [x] 全局 CSS Reset 已补充