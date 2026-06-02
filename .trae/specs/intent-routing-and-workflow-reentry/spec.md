# 智能体意图路由与工作流回退 Spec

## Why
当前市场洞察智能体无论用户输入什么内容，都会无差别地进入"数据采集 → 数据清洗 → 报告分析 → 报告导出"四阶段固定流水线。这导致两个核心问题：
1. **非洞察类问题误触发**：用户提问"你能做什么？""今天天气如何？""计算半径为10的球体面积"等无关问题时，依然会触发完整的搜索、爬取、分析流程，浪费计算资源和时间，且产出无意义报告。
2. **流程不可回退**：整个流水线执行完毕后，如果用户对报告质量不满意（如分析不够详细、数据不准确），无法跳回特定阶段重新执行，必须从头开始，导致灵活性差、用户体验差。

## What Changes
- **新增意图分类阶段**：在进入流水线前，通过 LLM 对用户输入进行意图分类，判断是否为市场洞察类请求
- **新增直接应答路径**：非洞察类请求直接由 LLM 应答，不进入流水线
- **新增工作流回退能力**：支持用户在流水线完成后，跳回报告分析、数据分析或数据采集阶段重新执行，并携带用户补充的约束信息
- **重构 Orchestrator**：将整体编排拆分为可独立调用的阶段操作，支持从任意阶段切入执行

## Impact
- Affected specs: 无（新特性）
- Affected code:
  - `backend/app/agents/orchestrator.py` — 重构为支持分阶段切入
  - `backend/app/services/workflow.py` — 新增意图分类、直接应答、回退流
  - `backend/app/api/routes/workflow.py` — 新增 `/start` 的意图分类逻辑、新增回退端点
  - `backend/app/schemas/agent.py` — 新增意图分类相关 Schema
  - `frontend/src/views/WorkflowView.vue` — 支持回退交互 UI
  - `frontend/src/stores/workflow.ts` — 支持回退事件
  - `frontend/src/api/services/workflow.ts` — 新增回退 API

## ADDED Requirements

### Requirement: 意图分类
系统 SHALL 在用户输入进入流水线之前，通过意图分类器判断用户输入的意图类型。

#### Scenario: 市场洞察类请求
- **WHEN** 用户输入包含市场分析、行业趋势、竞争格局、产品分析等洞察主题（如"2025年AI芯片市场趋势"）
- **THEN** 意图分类器返回 `intent_type = "market_insight"`，系统进入正常流水线

#### Scenario: 一般问答类请求
- **WHEN** 用户输入为一般性问题（如"你能做什么？""今天天气怎么样？""计算半径10的球体面积"）
- **THEN** 意图分类器返回 `intent_type = "general_question"`，系统直接通过 LLM 应答，不进入流水线

#### Scenario: 对已完成报告的追问
- **WHEN** 用户在已有报告结果后输入"分析不够详细，请重新分析"或"数据不够准确，需要重新采集"
- **THEN** 意图分类器识别为 `intent_type = "workflow_reentry"`，并识别目标阶段（`analyze` 或 `collect`）

### Requirement: 直接应答
系统 SHALL 对非洞察类请求提供直接 LLM 应答，不经过搜索、采集、清洗流程。

#### Scenario: 一般问题直接应答
- **WHEN** 意图分类结果为 `general_question`
- **THEN** 系统调用 LLM 直接生成回答，以 SSE 流式返回给前端，不展示四阶段进度条，直接显示回答内容

### Requirement: 工作流回退
系统 SHALL 支持在流水线完成后，用户可以从已完成的工作流中回退到指定阶段重新执行，并携带用户补充的约束信息。

#### Scenario: 回退到报告分析阶段
- **WHEN** 用户对已完成报告不满意，要求"报告分析不够详细，请加入更多数据支撑"
- **THEN** 系统识别回退目标为 `reporting` 阶段，复用已有的分析结果（AnalyzerOutput），重新调用 ReporterAgent 生成报告，并在 prompt 中注入用户的补充约束（"加入更多数据支撑"）

#### Scenario: 回退到数据分析阶段
- **WHEN** 用户对已完成报告的分析深度不满意，要求"分析维度不够全面，重新分析"
- **THEN** 系统识别回退目标为 `analyzing` 阶段，复用已有的清洗数据（CleanedItems），重新调用 AnalyzerAgent 进行分析，并将用户补充的约束注入分析 prompt，完成后自动继续执行 reporting 阶段

#### Scenario: 回退到数据采集阶段
- **WHEN** 用户发现数据不准确或不够详细，要求"数据存在虚假信息，请重新搜索并限制来源为官方渠道"
- **THEN** 系统识别回退目标为 `collecting` 阶段，携带用户补充的搜索约束（如"官方渠道"），重新执行采集 → 清洗 → 分析 → 报告全流程

#### Scenario: 回退失败处理
- **WHEN** 回退执行过程中某个阶段失败
- **THEN** 系统保留当前阶段之前的成果，在失败阶段停止，向前端返回错误信息和部分结果

### Requirement: 上下文感知的回退
系统 SHALL 在回退时保留原始工作流的历史上下文，使后续阶段能感知到这是一次改进而非首次执行。

#### Scenario: 回退到分析阶段时保留上下文
- **WHEN** 用户回退到 analyzing 阶段
- **THEN** AnalyzerAgent 的 prompt 中包含原始分析结果作为参考，以及用户补充的改进要求

#### Scenario: 回退到采集阶段时保留上下文
- **WHEN** 用户回退到 collecting 阶段
- **THEN** CollectorAgent 的搜索 query 中包含用户补充的约束条件（如"官方渠道""仅限2025年"等）

## MODIFIED Requirements

### Requirement: 工作流启动流程
**原行为**：`POST /api/v1/workflow/start` 直接创建流水线并返回 workflow_id
**新行为**：`POST /api/v1/workflow/start` 先进行意图分类，根据分类结果走不同路径：
- `market_insight` → 创建流水线，返回 workflow_id（与现有行为一致）
- `general_question` → 不创建流水线，直接返回 LLM 应答（流式）
- `workflow_reentry` → 触发回退流程

### Requirement: Orchestrator 执行能力
**原行为**：`OrchestratorAgent.execute()` 只支持从 collecting 开始的全流程执行
**新行为**：`OrchestratorAgent.execute()` 支持 `start_stage` 参数，可从 `collecting`、`analyzing`、`reporting` 任一阶段切入执行，并接受 `reentry_context`（用户补充约束）和 `previous_output`（上一轮输出）参数