# 修复工作流意图分类与路由 Spec

## Why

存在两个联动的意图路由 Bug：

**Bug 1 — 新对话直接启动工作流超时**：`POST /api/v1/workflow/start` 调用 `IntentClassifier.classify()` 时，LLM 调用耗时 30 秒后 `ReadTimeout`，虽然 fallback 到 `market_insight` 能正常启动工作流，但 30 秒的阻塞等待让前端体验极差，且日志中刷出完整 traceback。

根因：`IntentClassifier._call_llm()` 的 timeout 硬编码为 30 秒，且 `_ensure_db_config()` 在 LLM 不可用时未能加载有效配置（Ollama 未启动时 `rumtime_config` 中 `llm_base_url` 为空字符串，导致 `_build_llm_config()` 生成的 URL 格式错误）。

**Bug 2 — 追问消息不经过意图分类**：`POST /api/v1/workflow/follow-up` 无条件设置 `is_direct_response = True`，不调用意图分类器。导致用户在"日常提问"之后再问"帮我分析AI芯片市场"时，仍然走直答通路，无法启动工作流。

根因：`follow-up` 端点的设计初衷是"对话延续"，但未区分"延续聊天"和"新洞察请求"——用户在一轮对话中可能同时闲聊和发起分析任务。

## What Changes

- **修复** `IntentClassifier` 初始化与超时：LLM 不可用时仍能正常构造 URL（不崩溃），分类超时从 30s 降到 10s，fallback 前不再刷完整 traceback
- **修复** `POST /api/v1/workflow/follow-up` 路由：增加意图分类，`market_insight` 走工作流、`general_question` 走直答、`workflow_reentry` 走回退
- **修复** `IntentClassifier._call_llm` 的 tenacity 重试：`ReadTimeout` 也在重试白名单中，但 `stop_after_attempt(1)` 等于不重试，改为 `stop_after_attempt(2)` 并缩短 wait 间隔

## Impact

- Affected specs: `intent-routing-and-workflow-reentry`（兼容：原有市场洞察/直答/回退路由不变，follow-up 路径增强）
- Affected code: `backend/app/services/intent_classifier.py`, `backend/app/api/routes/workflow.py`, `backend/app/services/workflow.py`

## ADDED Requirements

### Requirement: IntentClassifier 初始化容错
`IntentClassifier.__init__()` SHALL 在 `llm_base_url` 为空字符串时使用 `settings.ollama_base_url` 作为默认值，避免 `_build_llm_config()` 构造出非法 URL 导致后续请求异常。

#### Scenario: Ollama 未启动时创建 IntentClassifier
- **WHEN** `rumtime_config` 中 `llm_base_url` 为空字符串
- **THEN** `IntentClassifier` 回退到 `settings.ollama_base_url`（`http://localhost:11434`）
- **THEN** `_build_llm_config()` 生成的 `self.llm_url` 为 `http://localhost:11434/api/generate`

### Requirement: 意图分类超时缩短
`IntentClassifier.classify()` SHALL 将 LLM 调用超时从 30 秒缩短为 10 秒，遇 `ReadTimeout` 时快速 fallback 到 `market_insight`，不在日志中打印完整 traceback。

#### Scenario: LLM 响应超时
- **WHEN** LLM 服务在 10 秒内未响应
- **THEN** `classify()` 返回 `{"intent_type": "market_insight", "confidence": 0.3, "reasoning": "Classification timeout, defaulting to market_insight"}`
- **THEN** 日志仅记录 `WARNING: Intent classification timeout, falling back to market_insight`，不打印 traceback

### Requirement: LLM 调用重试配置
`IntentClassifier._call_llm()` SHALL 使用 `stop_after_attempt(2)`，对 `ReadTimeout` 和 `ConnectError` 都触发重试，wait 使用固定 2 秒（而非指数退避），避免因重试放大延迟。

#### Scenario: 首次调用超时后重试成功
- **WHEN** 第一次 LLM 调用 10 秒后 `ReadTimeout`
- **THEN** 等待 2 秒后重试
- **THEN** 第二次调用在 10 秒内返回，使用成功结果

### Requirement: Follow-up 端点意图分类
`POST /api/v1/workflow/follow-up` SHALL 先调用 `IntentClassifier.classify()` 分类用户意图，根据结果分流：

- `market_insight` → 创建新工作流（`is_direct_response = False`），返回 `workflow_id` + `intent_type = "market_insight"`
- `general_question` → 保持现有行为，创建直答工作流（`is_direct_response = True`）
- `workflow_reentry` → 返回 `workflow_id` + `target_stage` + `user_feedback`

#### Scenario: 追问时发起市场洞察
- **WHEN** 用户在已有对话中发送"帮我分析2025年AI芯片市场趋势"
- **THEN** 意图分类返回 `market_insight`
- **THEN** follow-up 端点创建新工作流，返回 `workflow_id` 和 `intent_type = "market_insight"`
- **THEN** 前端触发 SSE 流式接收工作流进度

#### Scenario: 追问时继续闲聊
- **WHEN** 用户在已有对话中发送"你好，今天天气怎么样"
- **THEN** 意图分类返回 `general_question`
- **THEN** follow-up 端点保持现有行为，创建直答工作流

## MODIFIED Requirements

### Requirement: IntentClassifier 初始化
**原行为**：`__init__` 中 `self.llm_base_url = rumtime_config.get("llm_base_url")`，可能为空字符串
**新行为**：`__init__` 中 `self.llm_base_url = rumtime_config.get("llm_base_url") or settings.ollama_base_url`

### Requirement: Follow-up 端点行为
**原行为**：`POST /api/v1/workflow/follow-up` 无条件创建直答工作流
**新行为**：先进行意图分类，根据结果创建不同类型的工作流

## REMOVED Requirements

无。