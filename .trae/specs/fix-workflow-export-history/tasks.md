# 修复工作流导出报告错误 — 任务列表

# Tasks
- [x] Task 1: 修改 `handleExportReport` 逻辑 — 从 conversation.id 提取 workflow_id
  - [x] SubTask 1.1: 在 `WorkflowView.vue` 的 `handleExportReport` 函数中，添加从 `workflowStore.activeConversation?.id` 提取 `workflow_id` 的逻辑
  - [x] SubTask 1.2: 当 conversation.id 以 `server_` 前缀开头时去掉前缀，其余直接使用
  - [x] SubTask 1.3: 用提取到的 `workflow_id` 替代 `currentWorkflowId.value` 进行报告查询

- [ ] Task 2: 验证 — 确保新旧两种场景均可正常导出
  - [ ] SubTask 2.1: 测试新完成工作流导出（`currentWorkflowId` 有值）
  - [ ] SubTask 2.2: 测试历史对话导出（`currentWorkflowId` 为空）

# Task Dependencies
- [Task 1] 无依赖
- [Task 2] 依赖 [Task 1]