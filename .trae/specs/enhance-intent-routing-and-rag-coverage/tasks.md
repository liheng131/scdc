# 增强意图路由 · RAG 覆盖范围 · 主控 Agent 架构 — 任务列表

# Tasks

- [x] **Task 1**: 新增 `MasterAgent` 主控类（轻度重构）
  - [ ] SubTask 1.1: 在 `backend/app/agents/master_agent.py` 新建 `MasterAgent` 类，组合 `IntentClassifier` + `DirectResponseService` + `OrchestratorAgent` 引用
  - [ ] SubTask 1.2: 实现 `async def process_message(message, conversation_history, use_rag, ...) -> MasterDecision`，统一处理 4 类意图
  - [ ] SubTask 1.3: 在类 docstring 写明 4 种场景的主控动作 + 实际执行映射表
  - [x] SubTask 1.4: 修改 `WorkflowService` 改为持有 `MasterAgent` 实例；`_classify_intent()` 内部委托 `MasterAgent`，保持向后兼容
  - [ ] SubTask 1.5: **API 路由改造**：修改 `backend/app/api/routes/workflow.py` 的 `/start` 和 `/follow-up` 端点，改为调 `workflow_service.master_agent.process_message()` 拿 `MasterDecision`，再按 `decision.action` 分发（`orchestrate`/`direct`/`reentry`）。消除手写 `if intent_type == "general_question"` if/else。向后兼容：旧的 `WorkflowService._classify_intent()` 仍可作为内部辅助使用

- [x] **Task 2**: 修复意图分类器"上下文偏置" bug
  - [x] SubTask 2.1: 修改 `IntentClassifier._build_classification_prompt()` 顶部加"只看最新一条消息"指令
  - [x] SubTask 2.2: 在 `IntentClassifier.classify()` 中：若 confidence < 0.6，调一次 `_classify_without_history()` 仲裁
  - [x] SubTask 2.3: 实现"无历史分类"对比仲裁逻辑（启发式：无历史 confidence > 0.6 + 与带历史结果不一致 → 采用无历史）
  - [x] SubTask 2.4: 加端到端回归测试：模拟"复杂历史后问'你会做什么'"，验证分类 = `general_question`

- [x] **Task 3**: 直答（DirectResponse）可选 RAG
  - [x] SubTask 3.1: 配置存储改用 `rumtime_config`（key=`direct_response_rag`，默认 False）替代 system_settings 表（spec 调整）
  - [x] SubTask 3.2: 修改 `DirectResponseService.generate_response_stream()` 加 `use_rag: bool` 参数
  - [x] SubTask 3.3: `use_rag=True` 时：调 `VectorStoreService.search()` + `RerankService.rerank()`，把 top 3 片段注入 system prompt
  - [x] SubTask 3.4: 加 Milvus 不可用降级路径（try/except + logger.warning + 继续无 RAG 模式）
  - [x] SubTask 3.5: 修改 `routes/workflow.py` 的 `/start` / `/follow-up` 接受 `use_rag` 参数，从请求体读；缺省时回退 `rumtime_config.direct_response_rag`
  - [ ] SubTask 3.6: 前端 `SettingsView` / `AIModelsView` 加开关 UI（暂不在本任务范围）

- [x] **Task 4**: 报告写回 Milvus 时机改为 lazy
  - [x] SubTask 4.1: 在 `Report` model 加 `pending_vector_upload: bool` 和 `vector_uploaded_at: Optional[datetime]` 字段 + migration
  - [x] SubTask 4.2: 移除 `services/workflow.py` 中"工作流完成 → 立即嵌入 Milvus"的代码
  - [x] SubTask 4.3: 工作流完成时仅保存 Report 到 PostgreSQL，标记 `pending_vector_upload=True`
  - [x] SubTask 4.4: 在 `services/report.py` 新增 `upload_to_vector_store_if_pending(report_id)` 方法
  - [x] SubTask 4.5: 在 `routes/reports.py` 的 `/export` 端点调 `upload_to_vector_store_if_pending`
  - [x] SubTask 4.6: 在 `routes/reports.py` 的 `/upload` 端点调 `upload_to_vector_store_if_pending`（上传完成后）
  - [x] SubTask 4.7: 加 `services/vectorstore_upload.py` 抽出"分块 + 嵌入 + 写 Milvus"公共方法（消除 `report.py` / `workflow.py` 重复代码）

- [ ] **Task 5**: 同会话多轮 context 链路端到端验证
  - [ ] SubTask 5.1: **编写端到端测试** `backend/tests/test_e2e_context_chain.py`：用 `httpx.AsyncClient` 或直接调 service 层，模拟"已完成工作流对话 → 追问"流程，断言 LLM request 中 `messages` 数组含历史
  - [ ] SubTask 5.2: 检查 `WorkflowView.vue` 的 `sendMessage()` 中 `conversationHistory` 构造是否包含所有历史消息（覆盖：user 消息 + assistant 消息）
  - [ ] SubTask 5.3: 检查 `workflow.py` 的 `run_follow_up_stream()` 是否透传 `conversation_history` 到 `DirectResponseService`
  - [ ] SubTask 5.4: 检查 `DirectResponseService._stream_gpustack()` / `_stream_ollama()` 的 `messages` 数组拼接逻辑
  - [ ] SubTask 5.5: 检查 `use_rag=True` 时 system prompt 是否同时含历史 + RAG 片段
  - [ ] SubTask 5.6: 修正发现的链路断点（如有），写最小修复
  - [ ] SubTask 5.7: 在测试通过后，更新 checklist 标记完成

- [ ] **Task 6**: 验证
  - [ ] SubTask 6.1: 单元测试 `MasterAgent.process_message()` 4 种场景
  - [ ] SubTask 6.2: 单元测试 `IntentClassifier.classify()` 仲裁逻辑
  - [ ] SubTask 6.3: 单元测试 `DirectResponseService` RAG 开关
  - [ ] SubTask 6.4: 端到端测试 "复杂历史后问'你会做什么'" → 走直答
  - [ ] SubTask 6.5: 端到端测试 "工作流完成 → 导出报告 → Milvus 写入" 链路
  - [ ] SubTask 6.6: 端到端测试 "工作流完成 → 不导出 → Milvus 无写入"
  - [ ] SubTask 6.7: 端到端测试 "直答 RAG 开启 → 检索到相关历史 → LLM 引用"

# Task Dependencies

- [Task 1] 无依赖，优先
- [Task 2] 依赖 [Task 1]（MasterAgent 引用 IntentClassifier，但本 Task 仅修改 IntentClassifier 本身，可独立）
- [Task 3] 依赖 [Task 1]（MasterAgent 调用 DirectResponseService 时透传 use_rag），但 DirectResponseService 本身修改可独立
- [Task 4] 独立（动 Report / workflow / reports 三个模块，不动 Agent）
- [Task 5] 独立
- [Task 6] 依赖 [Task 1, 2, 3, 4, 5]
