# 修复追问功能 - 架构匹配计划

## 问题分析

### 当前状态
1. **前端调用链路**：
   - `workflowApi.followUp()` 使用 axios POST 到 `/api/v1/workflow/follow-up`
   - 期望返回 `{ code: 0, data: { workflow_id: "..." } }` (JSON)
   - 拿到 `workflow_id` 后再调用 `workflowStore.startWorkflowStream()` 打开 SSE 连接

2. **后端当前实现**：
   - `/follow-up` 直接返回 `StreamingResponse` (SSE 流)
   - content-type 为 `text/event-stream`
   - 前端 axios 尝试将 SSE 原始文本解析为 JSON → **解析失败**

3. **日志证据**：
   - 后端 `follow-up` 返回 HTTP 200（实际是 SSE 流）
   - 后端 LLM 调用成功（`DirectResponseService generating response`）
   - 前端报 `追问失败，请重试`（axios 的 catch 捕获到 JSON 解析异常）

### 根因
前后端架构不匹配：
- `/start` 端点正确：先返回 JSON `{ workflow_id }`，然后前端独立打开 SSE 流
- `/follow-up` 端点错误：直接返回 SSE 流，前端期望 JSON

### 解决方案
将 `/follow-up` 改造为与 `/start` 一致的模式：
1. 后端 `/follow-up` 改为返回 JSON（包含 `workflow_id`），SSE 流由 `/{workflow_id}/stream` 统一处理
2. 前端无需修改（已经是正确的调用模式）

## 修改内容

### 文件 1: `backend/app/api/routes/workflow.py`
**修改 `follow_up_workflow` 函数（第 87-109 行）**

**What**: 将 StreamingResponse 改为返回 JSON，与 `/start` 保持一致
**Why**: 前端 axios 期望 JSON 格式 `{ code: 0, data: { workflow_id } }`
**How**: 
```python
@router.post("/follow-up")
async def follow_up_workflow(
    req: FollowUpRequest,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    state = await workflow_service.create_workflow(
        topic=req.message,
        max_items=0,
        dimensions=[],
    )
    state.is_direct_response = True
    return success_response(data={
        "workflow_id": state.workflow_id,
        "topic": state.topic,
    })
```
- 移除 `StreamingResponse` 返回
- 设置 `state.is_direct_response = True`（让 stream 端点走 direct_response 路径）
- 使用 `get_current_active_user`（非 SSE 依赖）
- 返回 JSON 响应

### 文件 2: `backend/app/services/workflow.py`
**修改 `run_follow_up_stream` 方法（第 68-97 行）**

**What**: 简化为仅通过 direct_response 生成回复，不需要额外的 stage 事件
**Why**: `run_follow_up_stream` 已不再被路由直接调用，改为由 `run_workflow_stream` 统一处理（通过 `is_direct_response` 标记）
**How**: 实际上这个方法是多余的。`is_direct_response=True` 时，`run_workflow_stream` 第 139-149 行已经处理了 direct_response 模式。

**决策**：删除 `run_follow_up_stream` 方法，因为不再需要。`is_direct_response=True` 的 workflow 通过现有的 `/stream` 端点处理。

### 文件 3: `backend/app/api/routes/workflow.py`
**清理无用的 import**
- 移除 `StreamingResponse` import（如果不再使用）

## 验证步骤
1. 前端输入问题 → 首次分析 → 等待完成
2. 输入追问 → 调用 `/follow-up` 返回 JSON `{ workflow_id }`
3. 前端打开 SSE 连接到 `/{workflow_id}/stream`
4. 后端走 `run_workflow_stream` → `is_direct_response` 分支
5. LLM 生成回复 → `direct_response_done` 事件
6. 前端收到 `direct_response_done` → 调用 `onCompleted` → `loading` 重置
