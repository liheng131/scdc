# 同会话多轮 context 链路 —— 发现的断点与修复

> 对应 spec：`.trae/specs/enhance-intent-routing-and-rag-coverage/`
> 对应任务：Task 5（SubTask 5.1 ~ 5.6）
> 测试文件：`backend/tests/test_e2e_context_chain.py`

## 总结

| 编号 | 严重度 | 位置 | 状态 |
|------|--------|------|------|
| #1   | **P0**（阻断） | `backend/app/services/workflow.py` | ✅ 已修复 |

---

## #1 【P0 阻断】`MasterAgent` 未导入导致全应用无法启动

### 现象
- 直接跑 `python -m pytest backend/tests/test_health.py` 会在 **collection 阶段**失败，错误：

  ```
  app\services\workflow.py:65: in __init__
      self.master_agent = MasterAgent(
  E   NameError: name 'MasterAgent' is not defined
  ```

- 同样的错误也会在 `app/api/routes/workflow.py` 导入 `workflow_service` 单例时触发，导致：
  - FastAPI 应用启动失败
  - 任何引用 `app.main:app` 的测试（`test_health.py` / `test_e2e_flow.py` / …）全部 fail
  - 整个 backend 进程无法启动

### 根因
`backend/app/services/workflow.py` 的 `WorkflowService.__init__()`（第 65 行）使用了 `MasterAgent`，
但文件顶部只 import 了 `IntentClassifier` / `DirectResponseService` / `OrchestratorAgent`，
**漏写** `from app.agents.master_agent import MasterAgent`。

```python
# backend/app/services/workflow.py  —— 修复前
from app.agents.orchestrator import OrchestratorAgent
from app.schemas.agent import OrchestratorInput
from app.services.intent_classifier import IntentClassifier
from app.services.direct_response import DirectResponseService
# ← 缺：from app.agents.master_agent import MasterAgent
```

而第 65 行：

```python
self.master_agent = MasterAgent(
    intent_classifier=self._intent_classifier,
    direct_response=self._direct_response,
)
```

### 修复（最小修改）
在 `backend/app/services/workflow.py` 顶部追加缺失的 import：

```python
from app.agents.orchestrator import OrchestratorAgent
from app.agents.master_agent import MasterAgent   # ← 新增
from app.schemas.agent import OrchestratorInput
from app.services.intent_classifier import IntentClassifier
from app.services.direct_response import DirectResponseService
```

### 验证
- `python -c "from app.services.workflow import WorkflowService; print('OK')"` → OK
- `python -m pytest tests/test_health.py -v` → 1 passed
- `python -m pytest tests/test_e2e_context_chain.py -v` → **5 passed**

### 建议
在 CI 流水线加一条 "smoke import" 任务（`python -c "import app.main"`），防止类似
"未导入即引用"被静默推到主分支。

---

## 端到端测试覆盖的链路（Task 5 验收用）

| 测试函数 | 覆盖链路 |
|----------|----------|
| `test_e2e_context_chain_history_passes_to_llm_payload` | DirectResponseService._stream_gpustack() 拼接 messages 数组（system + history + 当前 user） |
| `test_e2e_context_chain_use_rag_injects_context_into_system` | use_rag=True → VectorStore.search + Rerank + Embedding → 片段注入 system prompt |
| `test_e2e_context_chain_workflow_run_follow_up_passes_history` | WorkflowService.run_follow_up_stream() 把 conversation_history 透传给 DirectResponseService |
| `test_e2e_context_chain_workflow_follow_up_falls_back_to_state_history` | history=None 时回退使用 WorkflowState.conversation_history |
| `test_e2e_context_chain_workflow_view_conversation_history_contains_both_roles` | frontend/src/views/WorkflowView.vue 中 sendMessage() 构造 conversationHistory 时包含 user + assistant 角色 |

所有 LLM / RAG / Embedding HTTP 调用均通过 `AsyncMock` 风格的自定义 `_FakeAsyncClient` 拦截，
不依赖任何外部服务，可离线运行。
