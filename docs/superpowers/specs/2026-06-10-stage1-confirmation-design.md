# Spec 1: 数据采集阶段 Human-in-the-Loop 确认 — Design

> 创建日期: 2026-06-10
> 状态: 草案（待用户审阅）
> 范围: 5 个 spec 系列的第 1 个（聚焦**数据采集**阶段确认）

## Why

当前工作流是「数据采集 → 数据清洗 → 数据分析 → 报告生成」四阶段全自动管线。用户反馈：
1. **采集结果不透明**：用户无法看到采集到了什么资料就被推入下一阶段
2. **缺少干预机会**：用户无法补充内部资料 / 调整搜索词 / 删除垃圾源
3. **后续扩展性差**：报告阶段无法回溯到采集调整

本次 Spec 1 只解决**数据采集阶段**的「确认 + 编辑 + 重跑」能力。后续 4 个 Spec（清洗 / 分析 / 报告 / PPT 导出）将复制此模式。

## What Changes

### 新增能力
- 数据采集阶段结束后，**SSE 流正常结束**（非错误），workflow_run 进入 `awaiting_confirmation` 状态
- 前端自动弹出**通用确认弹窗**，显示采集到的源链接 + 内容预览
- 用户可选：
  - **接受** → 进入下一阶段（数据清洗）
  - **拒绝**（等价于重试）→ 重跑当前阶段
  - **添加手动 URL / 关键词** → 重跑采集阶段，新输入与原输入合并
  - **文字反馈** → AI 解析后调整搜索策略，重跑采集
- 状态机新增 `stage_state` 字段，后端不丢失任何中间数据

### 不做的事（明确范围）
- ❌ 不改 ReporterAgent / AnalyzerAgent / CleanerAgent 的核心逻辑
- ❌ 不实现其他 3 个阶段的确认（留待 Spec 2-4）
- ❌ 不实现附件上传（用户明确未选）
- ❌ 不实现源删除（用户明确未选）
- ❌ 不实现 PPT 导出优化（留待 Spec 5）

## 架构

### 状态机（核心）

```
                start
                  │
                  ▼
        ┌─────────────────┐
        │  collecting     │◄────────┐
        │  (running)      │         │ reject / edits / feedback
        └────────┬────────┘         │
                 │ stage done       │
                 ▼                  │
        ┌─────────────────┐         │
        │  collecting     │         │
        │  (awaiting_     │─────────┘
        │   confirmation) │
        └────────┬────────┘
                 │ accept
                 ▼
        ┌─────────────────┐
        │  cleaning       │  ← Spec 2 覆盖
        │  (running)      │
        └─────────────────┘
```

**状态枚举**：
- `running`：阶段正常执行中
- `awaiting_confirmation`：阶段已完成，等待用户确认
- `completed`：工作流全部完成
- `failed`：工作流失败（含用户取消）

### 数据流

```
1. POST /workflow/collect
   → 创建 workflow_run (stage=collecting, stage_state=running)
   → 返回 run_id + SSE stream url

2. SSE 流推送阶段进度
   → {"event": "stage_complete", "stage": "collecting", "output": {...}}
   → SSE 流正常结束（status=200）
   → workflow_run.stage_state = 'awaiting_confirmation'

3. 前端读 /workflow/{id}/status
   → 看到 stage_state=awaiting_confirmation
   → 弹出确认弹窗

4. 用户在弹窗中：
   a) 点击「接受」→ POST /workflow/{id}/confirm {decision: "accept"}
   b) 点击「拒绝」→ POST /workflow/{id}/confirm {decision: "reject", user_feedback: "..."}
   c) 添加 URL/关键词 → POST /workflow/{id}/confirm {decision: "reject", user_edits: {...}}
   d) 文字反馈 → POST /workflow/{id}/confirm {decision: "reject", user_feedback: "..."}

5. 后端处理 confirm：
   - accept → 触发下一阶段（cleaning）的 SSE 流
   - reject（无论带不带 edits/feedback）→ 重跑当前阶段（collecting）的 SSE 流
     - 新一轮：workflow_run.stage_state=running
     - 老的 stage_output 保留在 stage_history JSON 字段

6. 重复 1-5 直到用户接受
```

## 数据模型

### `workflow_runs` 表加 3 个字段

```sql
ALTER TABLE workflow_runs ADD COLUMN stage_state VARCHAR(32) NOT NULL DEFAULT 'running';
ALTER TABLE workflow_runs ADD COLUMN stage_output JSON;        -- 当前阶段输出（待确认内容）
ALTER TABLE workflow_runs ADD COLUMN stage_history JSON;       -- 历史重试记录（数组）
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `stage_state` | enum | `running` / `awaiting_confirmation` / `completed` / `failed` |
| `stage_output` | JSON | 当前阶段输出（采集到的源列表、清洗后的数据等） |
| `stage_history` | JSON | `[{stage, output, decision, user_edits, user_feedback, timestamp}, ...]` |

**SQLAlchemy ORM 改动**（[models/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/models/workflow.py)）：
```python
class StageState(str, enum.Enum):
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"

class WorkflowRun(Base):
    # ... 现有字段 ...
    stage_state: Mapped[str] = mapped_column(String(32), default="running")
    stage_output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    stage_history: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
```

## API 契约

### 新增端点

#### `POST /api/v1/workflow/{run_id}/confirm`

**请求体**：
```json
{
  "decision": "accept" | "reject",
  "user_edits": {
    "extra_urls": ["https://internal.example.com/report.pdf"],
    "extra_keywords": ["AI 芯片", "算力供给"]
  },
  "user_feedback": "请多搜索学术论文，2025年Q1数据"
}
```

**字段语义**：
- `decision=accept` → 进入下一阶段
- `decision=reject` → 重跑当前阶段
  - `user_edits` 非空 → 与原 topic 合并后重跑
  - `user_feedback` 非空 → AI 解析后调整搜索策略重跑
  - 两者都为空 → 完全重跑（与拒绝但不带信息等价）

**响应**（202 Accepted）：
```json
{
  "run_id": "uuid-xxx",
  "stage": "cleaning",        // 下一阶段名（accept）或当前阶段名（reject）
  "stage_state": "running",
  "sse_url": "/api/v1/workflow/{run_id}/stream"
}
```

**错误**：
- 404：run_id 不存在
- 409：当前 stage_state 不是 awaiting_confirmation（无法重复 confirm）
- 500：后端处理失败

#### `GET /api/v1/workflow/{run_id}/status`

**用途**：前端轮询 / SSE 结束后查询状态

**响应**：
```json
{
  "run_id": "uuid-xxx",
  "stage": "collecting",
  "stage_state": "awaiting_confirmation",  // 关键字段
  "stage_output": {                        // 阶段输出（待确认）
    "sources": [
      {"url": "https://...", "title": "...", "snippet": "...", "score": 0.92}
    ]
  },
  "stage_history": [                       // 历史重试记录
    {"stage": "collecting", "decision": "reject", "user_feedback": "...", "timestamp": "..."}
  ]
}
```

### 修改端点

#### `POST /api/v1/workflow/collect`（采集阶段入口）

**改动**：
- 创建 workflow_run 时设 `stage_state='running'`
- SSE 流结束时（阶段完成）设 `stage_state='awaiting_confirmation'`（不再直接进入 cleaning）
- SSE 流中新增事件 `{"event": "stage_complete", "stage": "collecting", "output": {...}}`

## 前端组件

### `<StageConfirmDialog>` 通用组件

**位置**：`frontend/src/components/workflow/StageConfirmDialog.vue`

**Props**：
```typescript
interface Props {
  visible: boolean
  stage: string                              // 当前阶段名
  stageOutput: any                           // 阶段输出（采集到的源列表）
  loading: boolean                           // 提交中
}
```

**Emits**：
```typescript
emit('confirm', { decision, userEdits, userFeedback })
emit('cancel')                                // 关闭弹窗（不操作）
```

**内部 UI 结构**（针对 stage='collecting' 定制）：

```
┌─────────────────────────────────────────────┐
│  📋 数据采集结果确认                          │
├─────────────────────────────────────────────┤
│                                             │
│  本次采集到 N 个信息源，请审阅：              │
│                                             │
│  ┌─────────────────────────────────┐        │
│  │ ✓ 链接 1（AI 芯片市场规模）         │        │
│  │   https://example.com/...        │        │
│  │   「相关摘要片段...」              │        │
│  └─────────────────────────────────┘        │
│  ┌─────────────────────────────────┐        │
│  │ ✓ 链接 2                         │        │
│  └─────────────────────────────────┘        │
│  ...                                        │
│                                             │
│  ▼ 补充资料（可选）                          │
│  [ + 添加 URL ] [ + 添加关键词 ]              │
│                                             │
│  ▼ AI 调整建议（可选）                       │
│  [ 文字反馈给 AI，让其重新采集 ]               │
│                                             │
│  [ 拒绝重试 ]      [ 接受并继续 → ]          │
└─────────────────────────────────────────────┘
```

**状态管理**（Pinia）：
- `useWorkflowStore.confirm(runId, payload)` 调用 API
- 成功后根据响应中的 `sse_url` 重新订阅 SSE 流

### `WorkflowView.vue` 集成

**改动**：
- 监听 SSE `stage_complete` 事件
- 当事件触发时，自动设置 `dialogVisible=true`
- `dialog` 关闭（confirm/cancel）后，根据 decision 决定是否启动新 SSE 流

## 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| SSE 流中断（网络断开） | 前端保留 `stage_state=awaiting_confirmation`，刷新后从 `/status` 读最新状态恢复弹窗 |
| 后端 confirm 失败 | 返回 500，前端弹 toast「确认失败，请重试」，弹窗不关闭 |
| 用户重复 confirm | 后端返回 409「当前阶段无需确认」，前端忽略 |
| 重跑次数过多（防刷） | 后端检查 `stage_history` 长度 ≥ 5 → 拒绝并返回 429「重试次数过多，请接受或取消」 |
| 后端 stage 启动失败 | workflow_run.stage_state='failed'，前端弹窗显示失败原因 |

## 测试

### 单元测试
- `test_workflow_state_transitions.py`：状态机各转换
- `test_workflow_confirm_endpoint.py`：
  - accept 路径
  - reject 路径（不带任何编辑）
  - reject + user_edits 路径
  - reject + user_feedback 路径
  - 重试次数超限（5 次）
  - 重复 confirm 返回 409

### 集成测试
- `test_e2e_stage1_confirmation.py`：
  - 完整 happy path：collecting → awaiting_confirmation → accept → cleaning 启动
  - 重试 path：collecting → awaiting_confirmation → reject → collecting 重新启动
  - 编辑 path：collecting → awaiting_confirmation → reject+user_edits → collecting 重新启动

### 手工验证清单
- [ ] 启动"2025年AI芯片市场"工作流
- [ ] 采集完成后弹窗出现
- [ ] 查看源列表
- [ ] 添加 1 个 URL
- [ ] 点击拒绝重试
- [ ] 新一轮采集完成，弹窗再次出现
- [ ] 这一次点击接受
- [ ] 进入数据清洗阶段（验证重试次数累加在 stage_history）

## 文件改动清单

### 后端（预计 6 个文件改动）
1. `backend/app/models/workflow.py` — 加 3 个字段 + StageState 枚举
2. `backend/app/api/routes/workflow.py` — 加 `/confirm` 端点 + 改 SSE 事件流
3. `backend/app/services/workflow.py` — 新增 `confirm_stage()` 方法 + 状态转换逻辑
4. `backend/app/agents/orchestrator.py` — 在 collecting 阶段结束后写 stage_output + 改 stage_state
5. `backend/app/schemas/workflow.py` — 新增 `ConfirmStageRequest` / `WorkflowStatusResponse` schema
6. `backend/alembic/versions/xxxx_add_stage_fields.py` — DB 迁移

### 前端（预计 3 个文件改动）
1. `frontend/src/components/workflow/StageConfirmDialog.vue` — 新建通用确认弹窗
2. `frontend/src/views/WorkflowView.vue` — 集成弹窗 + 监听 SSE
3. `frontend/src/stores/workflow.ts` — 新增 `confirm()` action

### 测试（预计 2 个新建）
1. `backend/tests/test_workflow_confirm.py`
2. `backend/tests/test_e2e_stage1_confirmation.py`

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 状态机引入并发问题（用户快速点击 accept 多次） | 后端 confirm 端点加状态锁：仅 awaiting_confirmation 状态可 confirm |
| 重试次数过多导致采集 API 配额耗尽 | 后端 5 次上限保护 |
| SSE 重订阅丢消息 | SSE 端点返回所有历史 stage_complete 事件，前端去重 |
| stage_output JSON 字段可能很大 | 数据库 TEXT 即可；如 > 1MB 考虑压缩或外部存储（不在 Spec 1 范围） |

## 后续 Spec 衔接

| Spec | 复用组件 | 改动点 |
|------|---------|--------|
| Spec 2: 数据清洗确认 | `<StageConfirmDialog>` | 加 `stage='cleaning'` 分支展示清洗后数据 |
| Spec 3: 数据分析确认 | `<StageConfirmDialog>` | 加 `stage='analyzing'` 分支 + **框架推荐选择** UI（嵌入弹窗） |
| Spec 4: 报告生成确认 | `<StageConfirmDialog>` | 加 `stage='reporting'` 分支 |
| Spec 5: PPT 导出 | 现有 export 端点 | 增强 generate_pptx 支持图片嵌入 |

## 验收标准

1. ✅ 用户启动工作流，采集完成后能看到确认弹窗
2. ✅ 用户能接受 → 进入清洗
3. ✅ 用户能拒绝（带/不带反馈）→ 重跑采集
4. ✅ 用户能添加 URL/关键词 → 重跑时合并输入
5. ✅ workflow_runs.stage_state 正确反映状态
6. ✅ stage_history 记录每次重试
7. ✅ 重复 confirm 返回 409
8. ✅ 重试超过 5 次返回 429
9. ✅ 所有现有 e2e 测试仍然通过
10. ✅ 新增 6+ 个单元 / 集成测试覆盖

---

## 待用户审阅项

1. **数据模型**：3 个新字段是否合理？是否需要拆分 stage_output / stage_history 到独立表？
2. **API 契约**：`/confirm` 端点的请求体结构是否符合预期？
3. **前端弹窗**：`<StageConfirmDialog>` 通用化设计是否能接受？还是希望每个阶段一个独立组件？
4. **测试覆盖范围**：6+ 单元/集成测试 + 手工清单，是否够用？
5. **范围确认**：附件上传、源删除、PPT 导出均**不在 Spec 1 范围**，是否接受？

审阅通过后，进入 writing-plans 阶段产出实现计划。
