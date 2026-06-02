# 修复意图路由集成与报告保存校验 Spec

## Why
上一轮意图路由与工作流回退的规范文档虽然通过了 checklist 验证，但实际代码并未真正写入磁盘——`services/workflow.py`、`agents/orchestrator.py`、`api/routes/workflow.py` 三个核心文件保持原始状态，没有任何修改。导致"你会做什么"等简单提问仍然走完整四阶段流水线。同时上线后发现两个额外问题：1) 报告自动保存时 `chart_images` 字段校验失败（传入了 ECharts 配置对象而非 `{title, base64}` 格式）；2) embedding 服务 DNS 解析失败导致嵌入向量为空。

## What Changes
- **重新实现意图路由集成**：将意图分类器、直接应答服务、回退流真正写入 `workflow.py`、`orchestrator.py`、`api/routes/workflow.py`
- **修复报告自动保存校验错误**：`chart_configs`（ECharts 配置对象，含嵌套 dict/list）与 `chart_images`（`[{title: str, base64: str}]`）是两个不同的数据，需正确传递
- **修复 embedding DNS 错误**：增加 embedding 服务对 ollama 不可用时的优雅降级，避免阻塞分析流程

## Impact
- Affected specs: `intent-routing-and-workflow-reentry`（重新实现其未落地部分）
- Affected code:
  - `backend/app/services/workflow.py` — 集成意图分类 + 直接应答 + 回退流 + 修复 chart_images 传递
  - `backend/app/agents/orchestrator.py` — 支持 start_stage / reentry_context / previous_output
  - `backend/app/api/routes/workflow.py` — 意图路由分流 + 新增 reentry 端点
  - `backend/app/services/embedding.py` — ollama 不可用时优雅降级

## ADDED Requirements

### Requirement: 意图路由真正集成到工作流服务
系统 SHALL 在 `WorkflowService` 中集成 `IntentClassifier` 和 `DirectResponseService`，使 `/start` 端点能根据意图分流。

#### Scenario: 一般问答走直接应答
- **WHEN** 用户输入"你会做什么"
- **THEN** `IntentClassifier.classify()` 返回 `intent_type = "general_question"`，系统直接调用 `DirectResponseService.generate_response_stream()` 流式返回 LLM 回答，不创建 WorkflowRun，不触发采集/清洗/分析/报告

#### Scenario: 市场洞察走正常流水线
- **WHEN** 用户输入"2025年AI芯片市场趋势"
- **THEN** `IntentClassifier.classify()` 返回 `intent_type = "market_insight"`，系统创建 WorkflowRun 并走完整四阶段

### Requirement: 报告自动保存时正确传递 chart_images
系统 SHALL 在 `state.result` 中存储 `chart_images`（渲染后的 base64 图片列表），并在自动保存时传递 `chart_images` 而非 `chart_configs`。

#### Scenario: 报告保存成功
- **WHEN** 流水线完成后自动保存报告
- **THEN** `ReportCreate.chart_images` 收到 `[{"title": "str", "base64": "str"}]` 格式的数据，pydantic 校验通过，报告成功入库

### Requirement: Embedding 服务优雅降级
系统 SHALL 在 embedding 服务（ollama）不可用时，不抛出异常阻塞分析流程，而是返回空嵌入向量并记录警告日志。

#### Scenario: Ollama 不可用
- **WHEN** embedding 服务调用 ollama 时遇到连接错误（DNS 解析失败、连接超时等）
- **THEN** `embed_texts_or_empty()` 捕获异常，返回空列表，记录 WARNING 日志，不影响分析流程继续执行

## MODIFIED Requirements

### Requirement: OrchestratorAgent.execute() 支持分阶段切入
**原行为**：只支持从 collecting 开始的完整四阶段执行
**新行为**：支持 `start_stage` 参数从 collecting / analyzing / reporting 切入，支持 `reentry_context` 注入各阶段 prompt，支持 `previous_output` 复用上一轮输出

### Requirement: WorkflowService 新增回退流和直接应答方法
**原行为**：只有 `run_workflow_stream()` 和 `run_follow_up_stream()`
**新行为**：新增 `_classify_intent()`、`run_direct_response_stream()`、`run_reentry_stream()` 三个方法

### Requirement: API 路由新增意图分流和 reentry 端点
**原行为**：`POST /start` 直接创建 workflow
**新行为**：先调用 `_classify_intent()` 进行意图分类，根据结果分流到直接应答、正常流水线、或回退流；新增 `POST /{workflow_id}/reentry` 端点