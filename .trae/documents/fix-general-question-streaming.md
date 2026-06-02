# 修复 general_question 流式响应前端无显示问题

## 问题诊断

后端日志显示意图分类正确（`general_question`），且 SSE 事件正常发出：
```
INFO:app.services.intent_classifier:Intent classification result: general_question, confidence=0.95
INFO:app.services.direct_response:DirectResponseService generating response for: '你会做什么...'
INFO:httpx:HTTP Request: POST `http://120.79.96.231:6003/v1/chat/completions`  "HTTP/1.1 200 OK"
```

**但前端页面没有显示任何回复**，因为前后端通信不匹配：

### 后端行为（`/api/v1/workflow/start`，[routes/workflow.py](file:///c:/Users/U0015856/Documents/trae_projects/scdc/backend/app/api/routes/workflow.py#L49-L58)）
- 当意图为 `general_question` 时，**直接返回 SSE StreamingResponse**
- 当意图为 `market_insight` 时，返回 JSON `{"workflow_id": "xxx"}`

### 前端行为（`workflowApi.start()`，[WorkflowView.vue](file:///c:/Users/U0015856/Documents/trae_projects/scdc/frontend/src/views/WorkflowView.vue#L109-L163)）
- 用 axios POST 请求，**等待 JSON 响应**
- 收到 `workflow_id` 后，再调用 `startWorkflowStream()` 通过 EventSource 连接 `/{workflow_id}/stream` 端点

### 问题根因
当返回 `general_question` 时，`/start` 端点直接返回 SSE 流，axios 会**一直等待完整的 HTTP 响应体**才能解析 JSON。SSE 是长连接，在 `direct_response_done` 事件发送前不会关闭，所以前端永远卡在 `await apiClient.post()` 这一步，不会走到 `startWorkflowStream()`。

## 修复方案（最小改动）

保持前端 `workflowApi.start()` 和 `startWorkflowStream()` 逻辑不变，修改后端使 `/start` **始终返回 JSON**，将 SSE 流统一走 `/{workflow_id}/stream` 端点。

### 步骤 1：修改后端 `/start` 端点

文件：`backend/app/api/routes/workflow.py` 第 41-82 行

当 `intent_type == "general_question"` 时，不再直接返回 `StreamingResponse`，而是：
1. 创建一个工作流记录
2. 返回 JSON 包含 `workflow_id` 和 `is_direct_response: true`

```python
if intent_type == "general_question":
    state = await workflow_service.create_workflow(
        topic=req.topic,
        max_items=0,
        dimensions=[],
    )
    return success_response(data={
        "workflow_id": state.workflow_id,
        "topic": state.topic,
        "is_direct_response": True,
    })
```

### 步骤 2：修改后端 `run_workflow_stream` 方法

文件：`backend/app/services/workflow.py` 第 137-270 行

`run_workflow_stream()` 在 SSE 流开始时检测 `is_direct_response` 标记：
- 如果是，调用 `direct_response_service` 生成流式 SSE 事件
- 如果不是，走正常四阶段流水线

新增 `WorkflowState.is_direct_response` 字段。

### 步骤 3：前端 `WorkflowView.startAnalysis()` 接收 SSE 事件

文件：`frontend/src/stores/workflow.ts` 第 161-239 行（`attachEventSourceListeners` 方法）

在 EventSource 监听器中新增 `direct_response` 和 `direct_response_done` 事件处理：

```typescript
es.addEventListener('direct_response', (e: any) => {
  const data = JSON.parse(e.data);
  if (activeConvIdForStream.value && activeAssistantIdxForStream.value >= 0) {
    const current = conv.messages[activeAssistantIdxForStream.value];
    updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
      content: (current?.content || '') + (data.content || ''),
      stageHint: '💬 正在回复...',
    });
  }
});

es.addEventListener('direct_response_done', (e: any) => {
  if (activeConvIdForStream.value) {
    updateMessage(activeConvIdForStream.value, activeAssistantIdxForStream.value, {
      stageHint: '',
    });
    updateConversationStatus(activeConvIdForStream.value, 'completed');
  }
  clearEventSource();
});
```

### 步骤 4：重新构建后端 Docker 镜像并重启

```powershell
docker compose build --no-cache backend
docker compose up -d backend
```

## 涉及文件
- `backend/app/api/routes/workflow.py` - 修改 `/start` 端点，general_question 返回 JSON 而非 StreamingResponse
- `backend/app/services/workflow.py` - `run_workflow_stream` 支持 direct_response 模式
- `backend/app/schemas/agent.py` - `WorkflowState` 新增 `is_direct_response` 字段
- `frontend/src/stores/workflow.ts` - 新增 `direct_response` / `direct_response_done` 事件监听