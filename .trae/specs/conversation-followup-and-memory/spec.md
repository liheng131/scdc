# 对话追问与记忆功能 Spec

## Why
当前系统中，用户在智能体工作流页面发送消息时，每次都会创建全新对话并触发完整四阶段工作流（收集→清洗→分析→报告），无法在当前对话中继续追问，也无法引用之前的对话上下文。用户需要能够：
1. 在同一对话中继续发送追问消息
2. 系统能够记住对话历史并在处理时参考上下文

## What Changes
- **前端**：区分"新主题"和"追问"两种发送模式，追问模式下复用当前对话而非创建新对话
- **前端**：发送追问消息时携带对话历史作为上下文
- **后端**：工作流服务接收可选的 conversation_history 参数
- **后端**：新增 /follow-up 流式接口，支持简单追问直接调用 LLM 快速响应
- **后端**：ReporterAgent 支持接收对话历史上下文，在报告生成时参考

## Impact
- Affected specs: fix-workflow-conversation-llm-export
- Affected code:
  - `frontend/src/views/WorkflowView.vue`
  - `frontend/src/stores/workflow.ts`
  - `frontend/src/api/services/workflow.ts`
  - `backend/app/services/workflow.py`
  - `backend/app/agents/reporter.py`
  - `backend/app/api/routes/workflow.py`

## ADDED Requirements

### Requirement: 对话内追问功能
系统 SHALL 允许用户在当前对话未完成或已完成的情况下继续发送追问消息。追问消息应作为新消息添加到当前对话中，而非创建新对话。

#### Scenario: 用户在已有对话中追问
- **GIVEN** 用户已完成一次市场分析，当前对话状态为 completed
- **WHEN** 用户在输入框输入追问问题并点击"发送追问"
- **THEN** 追问消息添加到当前对话的消息列表中，不会创建新对话

### Requirement: 追问上下文传递
系统 SHALL 在发送追问时将当前对话的历史消息作为上下文传递给后端，后端在处理追问时能够引用历史对话内容。

#### Scenario: 追问携带对话历史
- **GIVEN** 用户当前对话有 3 条历史消息（用户提问→AI回答→用户追问）
- **WHEN** 用户发送第 4 条追问消息
- **THEN** 后端收到包含前 3 条消息的 conversation_history 参数

### Requirement: 快速追问响应
系统 SHALL 提供 /follow-up 流式接口，对于简单追问（不触发完整工作流）直接调用 LLM 参考对话历史快速响应。

#### Scenario: 简单追问快速响应
- **WHEN** 用户发送"能详细解释一下刚才提到的XX吗？"
- **THEN** 系统通过 /follow-up 接口直接调用 LLM，30 秒内返回回答，不触发完整的四阶段工作流

## MODIFIED Requirements

### Requirement: startAnalysis 发送逻辑
WorkflowView.vue 的 startAnalysis 方法 SHALL 根据当前是否存在活跃对话及对话状态，决定是创建新对话还是追加到当前对话。

#### Scenario: 首次分析
- **GIVEN** 当前无活跃对话
- **WHEN** 用户输入主题并点击"开始分析"
- **THEN** 创建新对话，触发完整四阶段工作流

#### Scenario: 同一对话内追问
- **GIVEN** 当前存在活跃对话且状态为 completed 或 idle
- **WHEN** 用户输入追问消息并点击"发送追问"
- **THEN** 消息追加到当前对话，调用 /follow-up 接口获取快速响应

#### Scenario: 工作流执行中
- **GIVEN** 当前对话工作流正在执行中（status = running）
- **WHEN** 用户尝试发送新消息
- **THEN** 提示用户"分析进行中，请等待完成后再追问"

### Requirement: 工作流服务接口
WorkflowService.run_workflow_stream SHALL 接收可选的 conversation_history 参数，并将其传递给 ReporterAgent。

### Requirement: ReporterAgent 输入
ReporterInput SHALL 新增可选的 conversation_history 字段，ReporterAgent 在生成报告时参考历史对话内容。
