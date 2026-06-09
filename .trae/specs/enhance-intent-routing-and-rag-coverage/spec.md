# 增强意图路由 · RAG 覆盖范围 · 主控 Agent 架构 Spec

## Why

基于用户对当前智能体工作流 7 个核心问题的客观分析（见 `.trae/documents/objective-7-questions-analysis.md`），当前架构存在 4 个关键缺口需要补齐：

1. **常规问题（直答）完全不查向量库** —— `DirectResponseService` 只调 LLM，`rag-analysis` spec 已确认"如要直答查 RAG 需在 DirectResponseService 中增加向量检索步骤"，但目前未实现
2. **报告写回 Milvus 时机过早** —— 当前在工作流报告生成完成时**自动**写回，但用户此时可能尚未满意，会把"用户不满意的版本"也写进向量库，污染后续 RAG 检索
3. **意图分类器有"上下文偏置" bug** —— 已有 spec `fix-intent-classification-and-routing` 把 `POST /follow-up` 接入分类器，**但未解决"前面刚跑完一个市场洞察（market_insight 上下文），再问一句'你会做什么'（明显 general_question）被误判为 market_insight"** 的问题。根因是 prompt 把 `conversation_history` 直接塞给 LLM，LLM 倾向于"延续上下文主题"
4. **"主控 Agent"概念不清** —— 目前 `IntentClassifier` 只是 `services/intent_classifier.py` 里的一个普通类，由 `WorkflowService` 调用，**不参与**常规问题的处理；`OrchestratorAgent` 也不处理直答。架构上没有一个真正的"主控"统一负责"分类 → 调 Orchestrator 或 DirectResponse → 记忆管理"

补充任务：
- **同会话多轮 context** 已能用（`conversation_history` 在前端 store / 后端 WorkflowState / SSE 都有传递），但需要新增一条端到端测试**固化**这条链路，避免回归
- **主控 Agent 轻量化重构**：把 `IntentClassifier` 提升为独立 `MasterAgent` 类，但保持向后兼容（`WorkflowService` 仍然能调用），不破坏已有 `fix-intent-classification-and-routing` / `intent-routing-and-workflow-reentry` / `conversation-followup-and-memory` 等 spec 已实现的路由能力

## What Changes

- **新增** `backend/app/agents/master_agent.py`：独立 `MasterAgent` 类，封装"意图分类 + 路由到 OrchestratorAgent / DirectResponseService + 记忆管理 + 上下文追踪"，对外暴露统一的 `process_message()` 入口
- **修改** `backend/app/services/direct_response.py`：新增可选 `use_rag: bool` 开关，开启时在调 LLM 之前检索 Milvus `scdc_reports` 中相关 top_k=3 历史报告片段，注入 system prompt
- **修改** `backend/app/services/intent_classifier.py`（继承 `MasterAgent`）：修复"上下文偏置"——新增"上下文隔离"提示词（明确告诉 LLM "**只根据最新一条消息判断**"），并在分类结果置信度 < 0.6 时**额外调用一次"无历史"分类器**做对比仲裁
- **修改** `backend/app/services/workflow.py`：报告完成时**不立即**写回 Milvus；改为在 `state.result` 中标记 `pending_vector_upload=True`，在以下两个时机真正写回：① 用户在 `POST /api/v1/reports/{id}/export` 导出报告时；② 用户在 `POST /api/v1/reports/upload` 上传报告时
- **修改** `backend/app/api/routes/reports.py`：导出/上传端点调 `_upload_to_vector_store()`
- **新增** `backend/app/services/vectorstore_upload.py`：封装"分块（chunk_size=512, overlap=64）→ 嵌入 → 写入 Milvus"流程，从 `workflow.py` / `report.py` 解耦
- **新增** `backend/app/core/conversation_context.py`：封装"同会话多轮 context 拼接 + 截断"工具函数，供 `MasterAgent` / `DirectResponseService` / `WorkflowService` 共用
- **修改** `frontend/src/views/SettingsView.vue`（或新建设置子页）：增加"直答是否启用 RAG"开关，持久化到 `system_settings` 表
- **修改** `frontend/src/views/WorkflowView.vue`：调用 `workflowApi.start` / `followUp` 时附加 `use_rag` 参数

## Impact

- **Affected specs**：
  - `intent-routing-and-workflow-reentry` —— 路由能力保留，`MasterAgent` 替代 `WorkflowService` 中的分类调用
  - `fix-intent-classification-and-routing` —— 兼容性保持，prompt 升级 + 双分类器仲裁
  - `reports-vector-upload` —— **写回时机从"工作流完成"改为"导出/上传"**
  - `conversation-followup-and-memory` —— 新增 `conversation_context.py` 复用
  - `rag-analysis` —— 直答 RAG 路径首次落地
  - `ai-model-config-management` —— 读取 `use_rag_for_direct_response` 系统设置
- **Affected code**（新增 + 修改）：
  - `backend/app/agents/master_agent.py` — **新增**
  - `backend/app/agents/orchestrator.py` — 不变，但 `MasterAgent` 会引用
  - `backend/app/services/intent_classifier.py` — 继承 `MasterAgent` 基类 / 工具方法
  - `backend/app/services/direct_response.py` — 加 `use_rag` 参数
  - `backend/app/services/workflow.py` — 报告写回时机改为 lazy
  - `backend/app/services/report.py` — 调 `vectorstore_upload` 替代内联嵌入
  - `backend/app/services/vectorstore_upload.py` — **新增**
  - `backend/app/core/conversation_context.py` — **新增**
  - `backend/app/api/routes/workflow.py` — 接受 `use_rag` 参数
  - `backend/app/api/routes/reports.py` — 导出/上传端点触发写回
  - `backend/app/models/system_settings.py` — 新增 `use_rag_for_direct_response` 字段
  - `frontend/src/api/services/workflow.ts` — `start` / `followUp` 加 `use_rag` 参数
  - `frontend/src/views/SettingsView.vue`（或新建 Settings/AIModelsView 子组件）— 开关 UI

## ADDED Requirements

### Requirement: MasterAgent 统一入口
系统 SHALL 提供 `MasterAgent` 类（位于 `backend/app/agents/master_agent.py`），作为"主控 Agent"对外暴露 `async def process_message(message, conversation_history, use_rag, ...) -> MasterDecision` 接口，根据意图分类结果返回 `{action: "orchestrate" | "direct" | "reentry", params: {...}}`。

#### Scenario: 主控调用
- **WHEN** `WorkflowService.run_workflow_stream()` 或 `DirectResponseService` 收到用户消息
- **THEN** 调用方应可改为调用 `MasterAgent.process_message()` 获取决策，再按 `decision.action` 分发

#### Scenario: 向后兼容
- **WHEN** 已有调用方仍调 `IntentClassifier.classify()` 或 `WorkflowService._classify_intent()`
- **THEN** 这些方法仍然可用，行为与现有 `fix-intent-classification-and-routing` spec 一致

### Requirement: 意图分类上下文偏置修复
`IntentClassifier._build_classification_prompt()` SHALL 在 prompt 顶部新增"**只根据用户最新一条消息判断意图；对话历史仅作为辅助参考，不要被历史话题影响**"的明确指令，并在置信度 < 0.6 时调用一次"无历史"分类做对比仲裁，取两者中更"合理"的分类（如果带历史判为 `market_insight`、无历史判为 `general_question`，且无历史版本置信度更高，则采用无历史版本）。

#### Scenario: 复杂历史后问"你会做什么"
- **WHEN** 对话历史最后一条是 `market_insight`（如"已生成 AI 芯片市场报告"），用户新发"你会做什么"
- **THEN** 分类器返回 `intent_type = "general_question"`，confidence > 0.6
- **THEN** 后端路由到 `DirectResponseService` 而非 `OrchestratorAgent`

#### Scenario: 分类置信度低时仲裁
- **WHEN** 带历史分类返回 `intent_type="market_insight", confidence=0.4`
- **THEN** 调无历史分类得到 `intent_type="general_question", confidence=0.8`
- **THEN** 最终采用 `general_question`

### Requirement: 直答 RAG 开关
`DirectResponseService.generate_response_stream()` SHALL 接收 `use_rag: bool` 参数；当 `use_rag=True` 时，在构造 system prompt 后插入"以下是从历史报告中检索到的相关内容片段：[top_k=3 片段]"段落，LLM 回答时会引用这些片段。

#### Scenario: 开启直答 RAG
- **GIVEN** 系统设置 `use_rag_for_direct_response=True`，且 Milvus 中有与"crm 是什么"相关的历史报告片段
- **WHEN** 用户问"crm 是什么"
- **THEN** DirectResponseService 检索 Milvus 得到 3 个相关片段
- **THEN** 注入 LLM prompt，LLM 回答中引用了这些片段

#### Scenario: 关闭直答 RAG
- **GIVEN** 系统设置 `use_rag_for_direct_response=False`
- **WHEN** 用户问"crm 是什么"
- **THEN** DirectResponseService 不检索 Milvus，直接调 LLM（与现状一致）

#### Scenario: Milvus 不可用降级
- **WHEN** DirectResponseService 调 RAG 时 Milvus 连接失败
- **THEN** 记录 WARNING 日志，自动降级为"无 RAG"模式继续回答，不抛异常

### Requirement: 报告写回 Milvus 改为 lazy
系统 SHALL **不**在工作流报告完成时自动写回 Milvus。改为在 `state.result` 中标记 `pending_vector_upload=True`，在以下时机真正写回：
- 用户首次 `POST /api/v1/reports/{id}/export` 导出报告（任意格式 PDF/DOCX/PPTX/MD）
- 用户在 `POST /api/v1/reports/upload` 上传报告时

#### Scenario: 工作流完成但未导出
- **WHEN** 工作流完成，自动保存报告到 PostgreSQL
- **THEN** 报告状态为 `pending_vector_upload=True`
- **THEN** **不**调 Milvus 写入
- **THEN** 用户在 UI 看到报告但未出现在 RAG 检索源中

#### Scenario: 用户首次导出 PDF
- **WHEN** 用户点击导出 PDF
- **THEN** 系统检查 `pending_vector_upload`，为 True 时调 `vectorstore_upload.upload_report(report_id)`
- **THEN** 标记 `pending_vector_upload=False`，`vector_uploaded_at=now()`

#### Scenario: 用户不满意报告重新生成
- **WHEN** 工作流回退到 `reporting` 阶段重新生成报告
- **THEN** 旧报告的 Milvus 向量（如果之前导出过）保留，**新报告**得到新 `report_id`，写回时按新 report_id 单独处理
- **THEN** 旧报告不被覆盖

### Requirement: 同会话多轮 context 链路端到端验证
系统 SHALL 端到端验证同会话多轮 context 传递链路：
1. 前端 store 记录历史消息
2. 发追问时把历史附给 `POST /follow-up`
3. 后端 `WorkflowState.conversation_history` 接收并透传给 `DirectResponseService.generate_response_stream(..., conversation_history=...)`
4. DirectResponseService 在构造 LLM messages 时把历史插入

#### Scenario: 端到端 context 测试
- **WHEN** 用户在已完成工作流的对话中追问"刚才提到的市场规模具体数据"
- **THEN** 后端日志显示 LLM request 中包含 `messages` 数组，前 N 条是对话历史
- **THEN** LLM 回答引用了之前报告中的数据

### Requirement: 文档化主控 Agent 职责
`MasterAgent` 文档 SHALL 明确以下职责分工（写在类 docstring 中）：

| 场景 | 主控 Agent 动作 | 实际执行 |
|------|----------------|----------|
| 常规问题 | 识别为 `general_question` → 调 `DirectResponseService`（可加 RAG） | DirectResponseService |
| 复杂问题 | 识别为 `market_insight` → 调 `OrchestratorAgent` 四阶段 | OrchestratorAgent |
| 追问/回退 | 识别为 `workflow_reentry` → 调 `OrchestratorAgent.execute(start_stage=...)` | OrchestratorAgent |
| 跨会话召回 | （暂未实现）调 `vectorstore_upload.search_cross_session()` | N/A |

#### Scenario: 文档可读
- **WHEN** 阅读 `master_agent.py` 的 docstring
- **THEN** 4 种场景的"主控动作 + 实际执行"一目了然

## MODIFIED Requirements

### Requirement: IntentClassifier 上下文处理
**原行为**：`_build_classification_prompt()` 把 `conversation_history` 直接塞给 LLM，LLM 易受历史偏置影响
**新行为**：
1. Prompt 顶部新增"只看最新一条消息"指令
2. 分类完成后，如果 confidence < 0.6，调一次"无历史"分类，对比两者结果
3. 取"无历史版本"中更合理的（用"无历史更保守"的启发式：若无历史 confidence 高 + 与带历史结果不一致，采用无历史）

### Requirement: 报告写回 Milvus 时机
**原行为**（按 `reports-vector-upload` spec）：工作流报告完成 → 自动嵌入 Milvus
**新行为**：工作流报告完成 → 仅写 PostgreSQL，标记 `pending_vector_upload=True`；导出/上传时真正写 Milvus

### Requirement: WorkflowService 与 IntentClassifier 关系
**原行为**：`WorkflowService` 直接持有 `IntentClassifier` 实例
**新行为**：`WorkflowService` 改为持有 `MasterAgent` 实例，`MasterAgent` 内部封装 `IntentClassifier`。`WorkflowService._classify_intent()` 仍可用（向后兼容，内部委托 `MasterAgent`）

## REMOVED Requirements

无。

---

## 关键决策点（实现阶段需要确认）

1. **`MasterAgent` 与 `IntentClassifier` 的关系**：是 `IntentClassifier` 继承 `MasterAgent`，还是 `MasterAgent` 组合 `IntentClassifier`？建议**组合**（更灵活，MasterAgent 还能组合其他服务）
2. **直答 RAG 的 top_k 选几**：建议 3（与 `analyzer.py` 现有 RAG 一致）
3. **分类器双调用仲裁的成本**：每次分类多一次 LLM 调用（10 秒超时），需要权衡准确率 vs 延迟。建议：仅在 confidence < 0.6 时启用仲裁，正常情况下不增加
4. **"未导出报告"如何清理**：如果用户生成报告后从不导出，Milvus 永远没有这条记录。是否需要后台任务定期清理 `pending_vector_upload=True` 且 `created_at < 30 天` 的报告？建议：v1 不做清理，让用户主动管理
5. **直答 RAG 检索时是否也走 RerankService**：建议走（与 `analyzer.py` 一致，质量更好但多一次 LLM 调用）
6. **`use_rag_for_direct_response` 系统设置的存储位置**：建议用 `system_settings` 表（key-value）而非新增专门表
7. **新 `MasterAgent` 是否改变前端调用方式**：建议不改变。前端继续调 `POST /start` / `POST /follow-up`，后端内部用 `MasterAgent` 路由
