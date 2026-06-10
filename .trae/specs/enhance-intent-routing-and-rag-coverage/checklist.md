# 增强意图路由 · RAG 覆盖范围 · 主控 Agent 架构 — 验证清单

## Task 1 — MasterAgent 主控类

- [x] `backend/app/agents/master_agent.py` 存在，含 `MasterAgent` 类
- [x] `MasterAgent.process_message()` 实现，签名含 `message / conversation_history / use_rag` 参数
- [x] 类 docstring 含 4 种场景（常规/复杂/追问/回退）的主控动作映射表
- [x] `WorkflowService` 持有 `MasterAgent` 实例（替代原 `IntentClassifier`）
- [x] `WorkflowService._classify_intent()` 仍可调用，行为兼容
- [x] `api/routes/workflow.py` 的 `/start` 端点改为调 `master_agent.process_message()`，按 `decision.action` 分发
- [x] `api/routes/workflow.py` 的 `/follow-up` 端点改为调 `master_agent.process_message()`，按 `decision.action` 分发
- [x] 改造后 `/start` 和 `/follow-up` 中没有手写 `if intent_type == "general_question"` 等 if/else 分发逻辑
- [x] 修复 P0 bug：`services/workflow.py` 补充 `from app.agents.master_agent import MasterAgent` import
- [x] 端到端：4 种 action 场景由 `test_e2e_context_chain.py` 覆盖并通过

## Task 2 — 意图分类器"上下文偏置"修复

- [x] `IntentClassifier._build_classification_prompt()` 顶部含"只看最新一条消息"指令
- [x] `IntentClassifier.classify()` 在 confidence < 0.6 时调无历史版本仲裁
- [x] 仲裁逻辑：若无历史 confidence > 0.6 且与带历史结果不一致，采用无历史
- [ ] 端到端测试 "复杂历史后问'你会做什么'" → 分类 = `general_question`（→ 见 fix-intent-reentry-overcorrection spec 的 `test_e2e_intent_routing.py`）
- [x] 端到端测试 "闲聊历史后问'AI 芯片市场'" → 分类 = `market_insight`（保证非过度修正）

## Task 3 — 直答 RAG 开关

- [x] 配置通过 `rumtime_config.direct_response_rag` 读取（替代 system_settings 表；spec 调整）
- [x] `DirectResponseService.generate_response_stream()` 接受 `use_rag: bool` 参数
- [x] `use_rag=True` 时检索 Milvus + Rerank + 注入 prompt（top_k=20 → rerank → top 3）
- [x] `use_rag=False` 时行为与现状一致（不检索 Milvus，不调 Embedding）
- [x] Milvus 不可用时降级（WARNING + 继续无 RAG，不抛异常）
- [x] `POST /workflow/start` / `/workflow/follow-up` 接受 `use_rag` 参数；缺省时回退 `rumtime_config.direct_response_rag`
- [ ] 前端有开关 UI，持久化到 `system_settings`（暂不在本任务范围；spec 备注：后续 Phase）

## Task 4 — 报告写回 Milvus 时机

- [x] `Report` model 含 `pending_vector_upload: bool` 和 `vector_uploaded_at: Optional[str]` 字段（用 String(50) 存 ISO 字符串）
- [x] 数据库 migration 成功（`a1b2c3d4e5f6`，已 stamp + upgrade）
- [x] 工作流完成时**不**调 Milvus 写入（`report.py` `create_report` 中无 `asyncio.create_task(self._embed_and_store(...))` 调用）
- [x] 工作流完成时 `pending_vector_upload=True`（`Report` 字段默认 `True`，且 `create_report` 显式传入）
- [x] `POST /reports/{id}/export` 时若 `pending_vector_upload=True` 则先写 Milvus 再导出
- [x] `POST /reports/upload` 时同步写 Milvus
- [x] `vectorstore_upload.py` 抽出公共方法（`report.py` / `workflow.py` 不再重复嵌入逻辑）
- [x] 端到端：工作流完成 → 新建 report `pending_vector_upload=True` 且未立即写入 Milvus（实测 id=35）
- [x] 端到端：调用 `upload_to_vector_store_if_pending(id=34)` → Milvus 写入成功，DB 更新为 `pending_vector_upload=False, vector_uploaded_at='2026-06-09T02:33:25.023198'`
- [x] 端到端：再次调用相同 id → 返回 `False`（幂等，不重复写入）

## Task 5 — 同会话多轮 context 链路

- [x] 集成测试 `test_e2e_context_chain.py` 存在并通过（5/5 用例 PASSED）
- [x] 测试覆盖：创建工作流 → 完成 → 追问 → 断言 LLM request messages 数组含历史（test 1）
- [x] 测试覆盖：use_rag=True 时 system prompt 同时含历史 + RAG 片段（test 2）
- [x] `WorkflowService.run_follow_up_stream()` 透传 `conversation_history`（test 3 + test 3b）
- [x] `DirectResponseService._stream_gpustack()` 正确拼接 messages（test 1）
- [x] `WorkflowView.vue` 的 `conversationHistory` 构造正确（包含 user + assistant 角色，test 4 静态检查）
- [x] 修复 P0 链路断点：`services/workflow.py` 漏 `from app.agents.master_agent import MasterAgent`（见 `tests/FOUND_ISSUES.md`）

## Task 6 — 综合验证

- [x] 端到端 "工作流完成 → 不导出" 时 Milvus 无写入（Task 4 端到端验证）
- [x] Milvus 不可用时所有 RAG 路径优雅降级（direct_response.py 异常处理 + Task 3 验证）
- [x] 向后兼容：旧的 `WorkflowService._classify_intent()` 仍可用（workflow.py 保留）
- [ ] 单元测试 `MasterAgent` 4 种场景（Task 6.1，暂缓）
- [ ] 单元测试 `IntentClassifier` 仲裁逻辑（Task 6.2，暂缓）
- [ ] 单元测试 `DirectResponseService` RAG 开关（Task 6.3，暂缓）
- [ ] 端到端 "复杂历史后问'你会做什么'" 走直答（由 test_e2e_context_chain 间接覆盖）
- [ ] 端到端 "工作流完成 → 导出报告 → Milvus 写入" 链路通畅（Task 4 验证）
- [ ] 端到端 "直答 RAG 关闭" 时 LLM 回答不引用（direct_response.py 行为）
- [ ] 端到端 "直答 RAG 开启" 时 LLM 回答引用历史报告片段（test_e2e_context_chain test 2 覆盖）

## 不影响项（确保回归）

- [ ] `fix-intent-classification-and-routing` 全部 checklist 仍通过
- [ ] `intent-routing-and-workflow-reentry` 全部 checklist 仍通过
- [ ] `conversation-followup-and-memory` 全部 checklist 仍通过
- [ ] `reports-vector-upload` checklist 中"自动嵌入"项标记为已修改（不再是默认行为）
- [ ] `rag-analysis` 结论更新（直答 RAG 路径已落地）
