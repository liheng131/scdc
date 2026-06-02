# Tasks

- [x] Task 1: 新增意图分类 Schema 与 IntentClassifier 服务
  - [x] 1.1 在 `schemas/agent.py` 中新增 `IntentType`（market_insight / general_question / workflow_reentry）、`IntentResult`、`ReentryTarget` 等 Schema
  - [x] 1.2 在 `backend/app/services/` 下新建 `intent_classifier.py`，实现 `IntentClassifier` 类，使用 LLM 对用户输入进行意图分类
  - [x] 1.3 IntentClassifier 的 prompt 需能区分三类意图：市场洞察、一般问答、工作流回退（含回退目标阶段识别）

- [x] Task 2: 重构 OrchestratorAgent 支持分阶段切入与回退
  - [x] 2.1 修改 `OrchestratorInput` 新增 `start_stage`（可选，默认 `collecting`）、`reentry_context`（可选，用户补充约束）、`previous_output`（可选，上一轮的部分输出）
  - [x] 2.2 修改 `OrchestratorAgent.execute()` 支持从 `collecting`、`analyzing`、`reporting` 任一阶段开始执行
  - [x] 2.3 当 `start_stage` 为 `collecting` 时，将 `reentry_context` 注入 CollectorAgent 的搜索 query
  - [x] 2.4 当 `start_stage` 为 `analyzing` 时，将 `reentry_context` 和 `previous_output` 注入 AnalyzerAgent 的 prompt
  - [x] 2.5 当 `start_stage` 为 `reporting` 时，将 `reentry_context` 注入 ReporterAgent 的 prompt

- [x] Task 3: 新增直接应答服务
  - [x] 3.1 在 `backend/app/services/` 下新建 `direct_response.py`，实现 `DirectResponseService` 类
  - [x] 3.2 实现 `generate_response_stream()` 方法，调用 LLM 直接生成回答并以 SSE 流式返回
  - [x] 3.3 前端 SSE 事件类型为 `direct_response`，包含 `content` 字段（增量文本）

- [x] Task 4: 修改 WorkflowService 集成意图分类与回退
  - [x] 4.1 修改 `WorkflowService.create_workflow()` 在创建流水线前调用 `IntentClassifier.classify()`
  - [x] 4.2 新增 `WorkflowService.run_direct_response_stream()` 方法，处理一般问答的流式应答
  - [x] 4.3 新增 `WorkflowService.run_reentry_stream()` 方法，处理回退流：根据回退目标阶段创建带 `start_stage` 的 OrchestratorInput，调用 `run_workflow_stream()` 但传入不同的 start_stage
  - [x] 4.4 修改 `WorkflowService.run_workflow_stream()` 支持传入 `start_stage` 和 `reentry_context`

- [x] Task 5: 修改 Workflow API 路由
  - [x] 5.1 修改 `POST /api/v1/workflow/start`：先进行意图分类，根据 `intent_type` 分流：
    - `market_insight` → 返回 workflow_id（现有行为）
    - `general_question` → 返回 `direct_response` 流
    - `workflow_reentry` → 返回回退流
  - [x] 5.2 新增 `POST /api/v1/workflow/{workflow_id}/reentry` 端点，接收 `target_stage` 和 `user_feedback`
  - [x] 5.3 修改 `GET /api/v1/workflow/{workflow_id}/stream` 支持回退流的 SSE 事件

- [x] Task 6: 前端适配回退交互
  - [x] 6.1 在 `WorkflowView.vue` 中，非市场洞察类问题的回答直接显示内容，不显示四阶段进度条
  - [x] 6.2 在报告完成后，报告卡片下方新增"不满意？重新分析""数据不准？重新采集"等回退按钮
  - [x] 6.3 点击回退按钮后弹出输入框，收集用户补充约束信息
  - [x] 6.4 前端 `workflow.ts` store 支持 `direct_response` SSE 事件
  - [x] 6.5 前端 `workflow.ts` API 层新增 `reentry` 方法

# Task Dependencies
- Task 2 依赖 Task 1（需要 Schema 定义）
- Task 4 依赖 Task 1、Task 2、Task 3
- Task 5 依赖 Task 4
- Task 6 依赖 Task 5
- Task 2 和 Task 3 可并行执行（互不依赖）