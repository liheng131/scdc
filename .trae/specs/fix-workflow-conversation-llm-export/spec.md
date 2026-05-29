# 智能体工作流修复 Spec

## Why
智能体工作流页面存在三个 bug：缺少新建对话功能导致用户无法重置界面开始新会话；LLM 模型服务不可用时 UI 提示不清晰且无法在设置页配置 LLM 服务地址；工作流输出报告后导出文件因 task_id 类型不匹配（字符串 vs int）导致报告从未写入数据库且导出始终失败。

## What Changes
- 在智能体工作流页面顶部添加"新建对话"按钮，点击后清空当前会话回到空状态
- 将 `llm_base_url` 纳入 runtime_config 管理，在系统设置页增加 LLM 服务地址字段和连接测试功能，后端新增 LLM 健康检查 API
- 修复 Report 模型的 `task_id` 字段类型从 `int ForeignKey` 改为 `Optional[str]`，同步修复 Schema、API 路由、前端查询的类型不匹配问题

## Impact
- Affected specs: add-report-export-and-settings
- Affected code:
  - `frontend/src/views/WorkflowView.vue` - 新增新建对话按钮和逻辑
  - `frontend/src/stores/workflow.ts` - 新增 resetActiveConversation 方法
  - `backend/app/core/runtime_config.py` - 新增 llm_base_url 配置项
  - `backend/app/api/routes/settings.py` - 新增 LLM 健康检查端点
  - `backend/app/agents/analyzer.py` - 改用 runtime_config 获取 llm_base_url
  - `backend/app/agents/reporter.py` - 改用 runtime_config 获取 llm_base_url
  - `backend/app/models/report.py` - task_id 改为 Optional[str]
  - `backend/app/schemas/report.py` - task_id 改为 Optional[str]，新增 workflow_id
  - `backend/app/api/routes/reports.py` - task_id 参数改为 Optional[str]
  - `backend/app/services/workflow.py` - _save_report 传入 workflow_id
  - `frontend/src/views/SettingsView.vue` - 新增 LLM 服务地址字段和测试按钮
  - `frontend/src/api/services/reports.ts` - task_id 改为 string 类型
  - `frontend/src/views/WorkflowView.vue` - 修复导出查询参数类型

## ADDED Requirements

### Requirement: 新建对话按钮
系统 SHALL 在智能体工作流页面提供"新建对话"按钮，允许用户清除当前会话并开始新分析。

#### Scenario: 用户点击新建对话
- **WHEN** 用户点击页面顶部的"新建对话"按钮
- **THEN** 当前对话区域清空，显示空状态初始界面（含建议话题标签）
- **AND** 输入框清空，用户可直接输入新话题

#### Scenario: 有正在执行的工作流时新建对话
- **WHEN** 用户在工作流执行中点击"新建对话"
- **THEN** 弹出确认框提示"当前分析正在进行，切换将丢失当前进度"
- **AND** 用户确认后中止当前 SSE 连接并清空界面

### Requirement: LLM 服务地址运行时配置
系统 SHALL 支持在系统设置页面配置 LLM 服务基地址，并支持连接测试验证服务可用性。

#### Scenario: 用户修改 LLM 服务地址
- **WHEN** 用户在系统设置页修改 LLM 服务地址并保存
- **THEN** 新地址立即生效，后续工作流使用新地址调用 LLM

#### Scenario: 用户测试 LLM 连接
- **WHEN** 用户点击"测试连接"按钮
- **THEN** 后端向 LLM 服务发送简单请求验证连通性
- **AND** 前端显示连接成功或失败的提示

#### Scenario: LLM 服务不可用时的工作流
- **WHEN** LLM 服务不可达
- **THEN** 工作流自动降级为规则分析/模板报告模式
- **AND** 系统设置页显示连接状态警告

### Requirement: 健康检查 API
系统 SHALL 提供 LLM 服务健康检查端点。

#### Scenario: 健康检查成功
- **WHEN** GET `/api/v1/settings/llm-health` 被调用
- **THEN** 返回 `{ "status": "ok", "model": "..." }` 表示 LLM 可用

#### Scenario: 健康检查失败
- **WHEN** GET `/api/v1/settings/llm-health` 被调用但 LLM 不可达
- **THEN** 返回 `{ "status": "unavailable", "error": "..." }` 表示 LLM 不可用

## MODIFIED Requirements

### Requirement: Report 模型 task_id 字段类型
Report 模型的 `task_id` 字段 SHALL 从 `int` ForeignKey 改为 `Optional[str]`，以兼容工作流引擎的字符串 UUID 风格 workflow_id。所有相关的 Schema、API 路由、前端查询参数同步修改。

#### Scenario: 工作流完成报告入库
- **WHEN** 工作流完成并触发 `_save_report`
- **THEN** 报告以 `workflow_id`（字符串）作为 task_id 写入数据库
- **AND** 不再因 Pydantic 类型校验失败而静默丢弃报告

#### Scenario: 前端按 workflow_id 查询报告进行导出
- **WHEN** 工作流页面点击导出按钮
- **THEN** 前端以字符串 workflow_id 查询报告列表
- **AND** 后端正确匹配并返回报告
- **AND** 导出文件正常下载

#### Scenario: 智能报告页面查询不区分 task_id 类型
- **WHEN** 智能报告页面查询报告列表
- **THEN** 兼容 task_id 为字符串的报告记录
- **AND** ReportOut.task_id 正确序列化为输出