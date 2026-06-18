# Spec 2: 全阶段 Human-in-the-Loop 确认

> 创建日期: 2026-06-10
> 关联 Spec: [Spec 1: 数据采集阶段确认](2026-06-10-stage1-confirmation-design.md)
> 状态: 待用户审核

## 1. 背景与目标

Spec 1 已实现 `collecting` 阶段的用户确认机制。本 Spec 扩展到全部 4 个阶段（collecting / cleaning / analyzing / reporting），形成一致的"边跑边确认"工作流，让用户对最终报告有完全的控制权。

**目标：**
1. 4 个阶段全部在完成后等待用户确认
2. 用户可在每阶段接受 / 重试（带反馈）/ 跳过
3. 用户可在工作流中途开启"本次剩余阶段自动接受"
4. 全局用户偏好可设"默认跳过所有确认"

**非目标：**
- 工作流暂停 / 跨天恢复
- 多用户协作同一工作流
- 移动端单独 UI

## 2. 范围决策

| 问题 | 决定 |
|------|------|
| 哪几个阶段加确认 | 4 阶段全做（collecting/cleaning/analyzing/reporting） |
| 用户编辑面 | 通用（接受/重试/跳过+文字反馈） + 各阶段定制（cleaning 勾选删除、reporting 富文本编辑） |
| 关闭弹窗行为 | 二次确认"确定离开？会接受当前结果" |
| 跳过模式 | 本次跳过（workflow 级缓存） + 全局跳过（用户设置） |
| 后端 SSE 端点 | 4 个 stage-specific 端点（`/stream-cleaning` 等） |
| 重试预算 | 统一 MAX_RETRY_PER_STAGE=3（每阶段 3 次） |
| 后端代码组织 | 1 个通用 `run_stage_only_stream(state, stage)` + 4 个 SSE 端点 |
| 前端组件 | 1 个通用 `StageConfirmDialog.vue` + 4 个内容渲染器（collecting/cleaning/analyzing/reporting） |

## 3. 状态机（不变）

```
collecting ─┐
cleaning   ─┤  RUNNING ──> AWAITING_CONFIRMATION ──[accept|skip]──> 下一阶段 RUNNING
analyzing  ─┤                                       ──[reject]──> 当前阶段 RUNNING (重试)
reporting  ─┘
```

`stage_state`、`stage_output`、`stage_history` 三个字段（Spec 1 已建）够用，**不新增 DB 字段**。

## 4. 后端架构

### 4.1 SSE 端点

| 端点 | 用途 | 状态 |
|------|------|------|
| `GET /api/v1/workflow/{id}/stream-collecting` | 跑 collecting | Spec 1 已有 |
| `GET /api/v1/workflow/{id}/stream-cleaning` | 跑 cleaning | **新增** |
| `GET /api/v1/workflow/{id}/stream-analyzing` | 跑 analyzing | **新增** |
| `GET /api/v1/workflow/{id}/stream-reporting` | 跑 reporting | **新增** |
| `POST /api/v1/workflow/{id}/confirm` | 用户决策 | Spec 1 已有，扩展 skip |

### 4.2 通用 stage runner

```python
async def run_stage_only_stream(
    self, state: WorkflowState, stage: str
) -> AsyncGenerator[str, None]:
    """通用: 跑指定 stage, 结束设 awaiting_confirmation.

    dispatch 表:
    - 'collecting' → CollectorAgent.execute()
    - 'cleaning'   → CleanerAgent.execute()
    - 'analyzing'  → AnalyzerAgent.execute()
    - 'reporting'  → ReporterAgent.execute()
    """
    # 1. 状态校验: state.stage_state == 'running' and state.current_stage == stage
    # 2. dispatch: 按 stage 调用对应 agent
    # 3. 写 stage_output (按 stage 序列化不同结构)
    # 4. 设 stage_state = 'awaiting_confirmation'
    # 5. SSE yield stage_complete 事件后流结束
```

4 个 SSE 端点都委托到这个方法。**含 `/stream-collecting`**：Spec 1 的 `run_collecting_only_stream` 内部逻辑会重构到此方法，行为不变（保持向后兼容，老客户端零影响）。

### 4.3 confirm_stage 扩展

`POST /api/v1/workflow/{id}/confirm` 的 `decision` 字段从 `Literal["accept", "reject"]` 扩展为 `Literal["accept", "reject", "skip"]`：

| decision | 行为 | 计入重试？ |
|----------|------|-----------|
| `accept` | 进入下一阶段 | 否 |
| `reject` | 重跑当前阶段 | 是（> 3 → 429） |
| `skip` | 直接接受当前 stage_output，进入下一阶段（不看预览） | 否 |

### 4.4 SSE 事件流（统一）

每个 stage 端点发送的事件序列：

```
event: stage_start     {stage, label}
event: stage_progress  {stage, percent, message}     # 多次
event: stage_complete  {stage, label, stage_state, stage_output}
event: error           {stage, error_message}        # 失败时
```

`stage_complete` 事件后流正常结束，客户端根据 `stage_output` 渲染弹窗。

### 4.5 用户编辑在各阶段的 schema

`user_edits` 用 `Optional[Dict[str, Any]]` 接收（不强制 schema 验证），各 stage 约定的键：

| Stage | user_edits 字段 | 说明 |
|-------|-----------------|------|
| collecting | `{extra_urls: [], extra_keywords: []}` | 已有 |
| cleaning | `{removed_item_ids: [str], min_content_length: int, language: str}` | 勾选删除 + 阈值 |
| analyzing | `{removed_insight_ids: [str], custom_dimensions: [str]}` | 删除 + 加维度 |
| reporting | `{edited_sections: Dict[str, str], removed_section_ids: [str], appended_sections: [str]}` | 富文本编辑：key=section heading, value=edited body |

### 4.6 stage_output 各阶段结构

| Stage | stage_output |
|-------|--------------|
| collecting | `{sources: [Source], warning: str}` |
| cleaning | `{cleaned_items: [CleanedItem], stats: {total_in, total_out, removed_count}}` |
| analyzing | `{insights: [Insight], dimensions: [str]}` |
| reporting | `{report: str (markdown), sections: [Section]}` |

### 4.7 stage_history 记录

每条记录：

```json
{
  "stage": "cleaning",
  "decision": "accept | reject | skip",
  "user_edits": {...},
  "user_feedback": "...",
  "timestamp": "2026-06-10T..."
}
```

## 5. 前端架构

### 5.1 组件树

```
StageConfirmDialog.vue            # 框架: 标题/状态条/关闭二次确认/底部按钮
├─ CollectingContentRenderer.vue  # 信源列表 + 补充 URL/关键词（**从现有 StageConfirmDialog.vue 抽出**）
├─ CleaningContentRenderer.vue    # 清洗后信源 + 勾选删除 + 阈值调整
├─ AnalyzingContentRenderer.vue   # 洞察列表 + 勾选删除 + 补充维度
└─ ReportingContentRenderer.vue   # 报告 markdown 预览 + 富文本编辑 + 章节增删
```

**抽取要求**：Spec 1 把 collecting 的信源列表、URL/关键词输入直接写在 `StageConfirmDialog.vue` 内。Spec 2 实施时**第一步**就是把这段逻辑抽到 `CollectingContentRenderer.vue`，并通过 props (`stageOutput`) 接收数据。dialog 框架保持不变。

### 5.2 Dialog 框架（不变部分）

- 顶部状态条：阶段名 + 标签 + "第 N 次确认" 标签
- 中间：动态内容区（4 个 renderer 之一）
- 折叠区"重试此阶段"：补充材料 + 文字反馈（Spec 1 风格）
- 底部按钮：
  - 取消（关闭触发二次确认）
  - 重试此阶段
  - 接受，继续
  - **新增勾选**："本次剩余阶段自动接受"

### 5.3 Pinia store 改造

`workflow.ts` 新增：

```typescript
const skipRemainingForWorkflow = ref<Set<string>>(new Set())  // 本次跳过
const userPreferences = ref({ skipAllConfirmations: false })  // 全局偏好

const STAGE_STREAM_URLS = {
  collecting: (id, token) => `/api/v1/workflow/${id}/stream-collecting?token=${token}`,
  cleaning:   (id, token) => `/api/v1/workflow/${id}/stream-cleaning?token=${token}`,
  analyzing:  (id, token) => `/api/v1/workflow/${id}/stream-analyzing?token=${token}`,
  reporting:  (id, token) => `/api/v1/workflow/${id}/stream-reporting?token=${token}`,
}
```

### 5.4 skip 决策树

收到 `stage_complete` 事件时：

```
if userPreferences.skipAllConfirmations:
  POST /confirm { decision: "skip" }
elif skipRemainingForWorkflow.has(workflowId):
  POST /confirm { decision: "skip" }
else:
  show ConfirmDialog with appropriate renderer
```

### 5.5 SSE 监听器切换

- 保留现有 `attachEventSourceListeners(es)` 框架
- 收到 `stage_complete` 后，根据 `next_stage` 字段动态关掉当前 EventSource，开新的
- 监听器不变，URL 动态拼接

## 6. 边界与错误

| 情况 | 处理 |
|------|------|
| SSE 流中途断网 | EventSource 不自动重连，提示"网络中断，请刷新"；DB stage_state 保持 running |
| 用户刷新页面 | 新增 `GET /api/v1/workflow/{id}/status` 端点查 stage_output + stage_state，UI 自动恢复弹窗 |
| 用户拒绝超过 3 次 | 后端返 429，提示"重试次数过多，请接受或取消工作流" |
| 并发 confirm（双击） | 后端 in-memory lock，第二次返 409 |
| 阶段间数据传递失败 | stage_state='failed'，SSE 推 error 事件 |
| 阶段运行时报错 | 同上，统一 error 处理 |

### HTTP 码

| 码 | 场景 |
|----|------|
| 200 | 正常 |
| 401 | 未认证 |
| 404 | workflow_id 不存在 |
| 409 | stage_state 不是 awaiting_confirmation |
| 422 | decision 非法 / user_edits 格式错 |
| 429 | retry 超 MAX_RETRY_PER_STAGE=3 |

## 7. 测试策略

| 层级 | 文件 | 覆盖 |
|------|------|------|
| 单元 | `test_stage_runner_generalized.py` | 通用 runner 状态机 / accept / reject / skip / 3次上限 |
| 单元 | `test_user_edits_per_stage.py` | 4 阶段 user_edits schema 解析 |
| 集成 | `test_cleaning_endpoint.py` | `/stream-cleaning` SSE 事件序列 + 409/422/429 |
| 集成 | `test_analyzing_endpoint.py` | `/stream-analyzing` |
| 集成 | `test_reporting_endpoint.py` | `/stream-reporting` + 最终报告格式 |
| 集成 | `test_confirm_skip.py` | skip 决策端到端 |
| 集成 | `test_workflow_status.py` | `/status` 端点（恢复弹窗用） |
| E2E | 手工 | 4 阶段完整流程 + skip 模式 + 关闭二次确认 |

## 8. 实施拆分（预估）

| 阶段 | 内容 | 文件 |
|------|------|------|
| Phase 1 | 后端通用 runner + 3 个新 SSE 端点 | `services/workflow.py` / `api/routes/workflow.py` |
| Phase 2 | 后端 confirm_stage 扩展 skip + status 端点 | 同上 |
| Phase 3 | 前端 Pinia store + 跳过逻辑 | `stores/workflow.ts` / `api/services/workflow.ts` |
| Phase 4 | 前端抽 CollectingRenderer + 新增 CleaningRenderer + AnalyzingRenderer + ReportingRenderer | 4 个 .vue（1 抽 3 新） |
| Phase 5 | 前端 StageConfirmDialog 改造（动态内容区 + 关闭二次确认 + skip 勾选） | `components/StageConfirmDialog.vue` |
| Phase 6 | 单元 + 集成测试 | 7 个测试文件 |
| Phase 7 | 手工 E2E + commit | - |

## 9. 风险与回退

| 风险 | 缓解 |
|------|------|
| 通用 runner 抽象遗漏 stage-specific 逻辑 | 保留 stage-specific hooks（`pre_run` / `post_run` 回调） |
| 前端 4 个 renderer 字段不同导致 UI 不一致 | 公共 props 接口 `StageContentProps` 强制规范 |
| skip 导致用户错过关键检查 | 弹窗关闭二次确认文案明确；首次跑工作流默认开确认 |
| retry 3 次仍不够 | 5.0 版本后再调；MVP 用户可接受"超过 3 次就接受" |

## 10. 关联

- Spec 1: 数据采集阶段确认（已完成，提供 state machine / 字段 / SSE 模式基础）
- 现有代码: `backend/app/services/workflow.py` / `app/api/routes/workflow.py` / `frontend/src/components/StageConfirmDialog.vue`
