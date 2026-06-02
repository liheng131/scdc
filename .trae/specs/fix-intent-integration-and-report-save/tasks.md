# Tasks

- [x] Task 1: 修复 `services/workflow.py` — 集成意图分类、直接应答、回退流，修复 chart_images 传递
  - [x] 1.1 新增 `from app.services.intent_classifier import IntentClassifier` 和 `from app.services.direct_response import DirectResponseService` 导入
  - [x] 1.2 `__init__` 中初始化 `self._intent_classifier` 和 `self._direct_response`
  - [x] 1.3 新增 `_classify_intent()` 方法，委托给 `IntentClassifier.classify()`
  - [x] 1.4 新增 `run_direct_response_stream()` 方法，委托给 `DirectResponseService.generate_response_stream()`
  - [x] 1.5 新增 `run_reentry_stream()` 方法，支持从指定阶段回退重新执行
  - [x] 1.6 `run_workflow_stream()` 新增 `start_stage` 和 `reentry_context` 参数，传递给 OrchestratorInput
  - [x] 1.7 修复 `state.result` 中存储 `chart_images`（reporter.chart_images），自动保存时传递 `chart_images` 而非 `chart_configs`

- [x] Task 2: 重构 `agents/orchestrator.py` — 支持分阶段切入与回退
  - [x] 2.1 `execute()` 方法新增 `start_stage` / `reentry_context` / `previous_output` 参数处理
  - [x] 2.2 当 `start_stage` 为 `collecting` 且有 `reentry_context` 时，将约束注入搜索 topic
  - [x] 2.3 当 `start_stage` 为 `analyzing` 时，从 `previous_output` 重建 CleanedItems，跳过采集+清洗
  - [x] 2.4 当 `start_stage` 为 `reporting` 时，从 `previous_output` 重建 AnalyzerOutput，跳过采集+清洗+分析
  - [x] 2.5 跳过阶段时不发送对应状态回调

- [x] Task 3: 修改 `api/routes/workflow.py` — 意图路由分流 + reentry 端点
  - [x] 3.1 `POST /start` 先调用 `workflow_service._classify_intent()` 进行意图分类
  - [x] 3.2 `general_question` → 返回 `StreamingResponse` 直接应答
  - [x] 3.3 `workflow_reentry` → 创建 workflow 并返回 `intent_type` / `target_stage` / `user_feedback`
  - [x] 3.4 `market_insight` → 原有行为，创建 workflow 返回 `workflow_id`
  - [x] 3.5 新增 `POST /{workflow_id}/reentry` 端点，接收 `target_stage` 和 `user_feedback`

- [x] Task 4: 修复 `services/embedding.py` — Ollama 不可用时优雅降级
  - [x] 4.1 `_embed_ollama()` 方法中，`httpx.ConnectError` 和 `httpx.RequestError`（含 DNS 解析失败）不向上抛出，而是返回空列表
  - [x] 4.2 确保 `embed_texts_or_empty()` 能正确捕获所有网络异常

# Task Dependencies
- Task 2 依赖 Task 1（需要 Schema 定义，但 Schema 已在 `intent-routing-and-workflow-reentry` 中完成）
- Task 3 依赖 Task 1
- Task 1、Task 4 可并行执行
- Task 2 和 Task 3 可并行执行（依赖 Task 1 完成）