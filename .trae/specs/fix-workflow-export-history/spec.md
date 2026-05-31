# 修复工作流导出报告错误 Spec

## Why

用户在工作流页面（无论是新生成的还是从历史记录加载的对话）点击导出 PDF/Word/PPT 格式时，前端报错"报告尚未完全生成，请稍后重试"。这是因为 `currentWorkflowId` 只在当前工作流完成时设置，从历史记录加载的对话 `currentWorkflowId` 为空，导致报告 ID 查询失败。

## What Changes

- **修复** 历史对话导出失败 — 从历史记录加载的对话可通过 `conversation.id` 提取 `workflow_id`，正确查询报告
- **优化** 新对话导出健壮性 — 当前工作流导出也改用从 `conversation.id` 提取 `workflow_id`，减少对 `currentWorkflowId` 的依赖

## Impact

- Affected specs: `fix-pipeline-issues-round2`
- Affected code: `frontend/src/views/WorkflowView.vue`, `frontend/src/stores/workflow.ts`

## ADDED Requirements

无。

## MODIFIED Requirements

### Requirement: 工作流导出报告 ID 解析
`handleExportReport` SHALL 能从当前活动对话的 `id` 字段中提取真实的 `workflow_id`（即 task_id），用于查询/创建报告。

#### Scenario: 从历史记录加载对话后导出
- **WHEN** 用户从历史记录中选择一个对话，然后点击导出 PDF
- **THEN** 系统从 `conversation.id` 中提取 `workflow_id`（格式为 `server_{workflow_id}` 时去掉前缀）
- **THEN** 通过 `task_id` 查询已有报告
- **THEN** 报告正常导出

#### Scenario: 当前完成的工作流导出
- **WHEN** 用户刚完成一个工作流分析，立即点击导出
- **THEN** 系统优先使用 `currentWorkflowId`，若无则回退到 `conversation.id` 提取 `workflow_id`
- **THEN** 报告正常导出

## REMOVED Requirements

无。