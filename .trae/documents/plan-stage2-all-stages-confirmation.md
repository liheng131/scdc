# Spec 2 实施计划：全阶段 Human-in-the-Loop 确认

> 创建日期: 2026-06-10
> 设计文档: [2026-06-10-stage2-all-stages-confirmation-design.md](file:///d:/project/trae_projects/scdc/docs/superpowers/specs/2026-06-10-stage2-all-stages-confirmation-design.md)
> 总工作量: 后端 2 文件改造 + 前端 5 文件改造/新增 + 7 测试文件

---

## Phase 1：后端通用 stage runner + 3 个新 SSE 端点

### Task 1.1：抽取通用 stage runner
- **文件**: [backend/app/services/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/services/workflow.py)
- **改动**:
  - 新增 `async def run_stage_only_stream(self, state, stage: str) -> AsyncGenerator[str, None]:`
  - 内部 dispatch 表（switch on stage）：
    - `collecting` → 调 `CollectorAgent.execute()`，序列化 `{sources, warning}`
    - `cleaning` → 调 `CleanerAgent.execute(raw_items=...)`，序列化 `{cleaned_items, stats}`
    - `analyzing` → 调 `AnalyzerAgent.execute(items=...)`，序列化 `{insights, dimensions}`
    - `reporting` → 调 `ReporterAgent.execute(insights=...)`，序列化 `{report, sections}`
  - 状态机流程（与现有 `run_collecting_only_stream` 一致）：
    - 校验 `state.stage_state == 'running'`
    - 跑 agent
    - 写 `state.stage_output`
    - 设 `state.stage_state = AWAITING_CONFIRMATION`
    - yield `stage_complete` 事件
- **重构**：把现有 `run_collecting_only_stream` 改为薄包装，内部委托 `run_stage_only_stream(state, 'collecting')` —— 行为不变
- **验证**: 跑 Spec 1 既有 `test_stage_confirmation.py` + `test_confirm_endpoint.py` 全数通过

### Task 1.2：3 个新 SSE 端点
- **文件**: [backend/app/api/routes/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/workflow.py)
- **新增端点**:
  ```python
  @router.get("/{workflow_id}/stream-cleaning")
  async def stream_cleaning(workflow_id, current_user=...):
      # 校验 workflow + 状态 → 委托 workflow_service.run_stage_only_stream(state, 'cleaning')

  @router.get("/{workflow_id}/stream-analyzing")
  async def stream_analyzing(workflow_id, current_user=...): ...

  @router.get("/{workflow_id}/stream-reporting")
  async def stream_reporting(workflow_id, current_user=...): ...
  ```
- **统一 404/409 错误处理**（参照现有 `/stream-collecting`）
- **验证**: 单元测试覆盖 404 / 409 / 200 SSE 流三类情况

### Task 1.3：MAX_RETRY_PER_STAGE 调整
- **文件**: [backend/app/services/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/services/workflow.py)
- **改动**: `MAX_RETRY_PER_STAGE = 5` → `MAX_RETRY_PER_STAGE = 3`
- **验证**: 既有 `test_stage_confirmation.py` 中超 5 次重试的用例需改为超 3 次

---

## Phase 2：后端 confirm_stage skip + status 端点

### Task 2.1：confirm_stage 扩展 skip 决策
- **文件**: [backend/app/services/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/services/workflow.py) + [backend/app/schemas/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/schemas/workflow.py)
- **改动**:
  - `ConfirmStageRequest.decision: Literal["accept", "reject"]` → `Literal["accept", "reject", "skip"]`
  - `confirm_stage()` 增加 `skip` 分支：
    - 不检查 `len(stage_history) >= MAX_RETRY_PER_STAGE`（skip 不算重试）
    - 行为同 `accept`：进下一阶段，写 `stage_history` 记录 `decision='skip'`
- **验证**: 单元测试 `test_confirm_skip` 覆盖 skip 行为

### Task 2.2：新增 status 端点（恢复弹窗用）
- **文件**: [backend/app/api/routes/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/workflow.py)
- **新增**:
  ```python
  class WorkflowStatusResponse(BaseModel):
      workflow_id: str
      stage: str
      stage_state: str
      stage_output: Optional[Dict[str, Any]] = None
      stage_history_length: int

  @router.get("/{workflow_id}/status")
  async def get_workflow_status(workflow_id, current_user=...):
      # 查 DB workflow_run → 返 status（无 SSE）
  ```
- **验证**: 集成测试覆盖 200 / 404 / 401

### Task 2.3：通用 stage runner 错误处理
- **文件**: [backend/app/services/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/services/workflow.py)
- **改动**:
  - 跑 agent 失败时设 `stage_state = FAILED`，yield `stage_error` 事件
  - 状态机 dispatch 失败时降级到 `collecting`（兜底）

---

## Phase 3：前端 Pinia store + 跳过逻辑

### Task 3.1：workflow store 改造
- **文件**: [frontend/src/stores/workflow.ts](file:///d:/project/trae_projects/scdc/frontend/src/stores/workflow.ts)
- **新增**:
  ```typescript
  const skipRemainingForWorkflow = ref<Set<string>>(new Set());
  const userPreferences = ref({ skipAllConfirmations: false });

  // 跳过模式开关
  const setSkipRemaining = (workflowId: string, on: boolean) => { ... }
  const setUserPreference = (key: string, value: any) => { ... }

  // skip 决策树（在 onStageComplete 中调用）
  const shouldAutoSkip = (workflowId: string): boolean => {
    return userPreferences.value.skipAllConfirmations
        || skipRemainingForWorkflow.value.has(workflowId);
  }
  ```
- **持久化**:
  - `userPreferences` 存 `localStorage`（全局）
  - `skipRemainingForWorkflow` 仅内存（本次工作流）

### Task 3.2：API service 扩展
- **文件**: [frontend/src/api/services/workflow.ts](file:///d:/project/trae_projects/scdc/frontend/src/api/services/workflow.ts)
- **新增**:
  ```typescript
  // 4 个 stage-specific SSE URL
  getStreamUrl: (workflowId, stage, token) => `/api/v1/workflow/${workflowId}/stream-${stage}?token=${token}`

  // Status 端点
  getWorkflowStatus: (workflowId) => apiClient.get(...)

  // Confirm 端点（已存在，扩展 decision 类型）
  // StageConfirmRequest.decision: 'accept' | 'reject' | 'skip'
  ```

---

## Phase 4：前端 4 个内容渲染器

### Task 4.1：抽取 CollectingContentRenderer
- **文件**: [frontend/src/components/stage-renderers/CollectingContentRenderer.vue](file:///d:/project/trae_projects/scdc/frontend/src/components/stage-renderers/CollectingContentRenderer.vue)（**新建**）
- **改动**:
  - 把现有 `StageConfirmDialog.vue` 内的"信源列表 + URL/关键词输入 + 文字反馈"逻辑抽到这里
  - Props: `stageOutput: { sources, warning }`, `userEdits: { extraUrls, extraKeywords }`
  - Emit: `update:userEdits`
- **同步改造**: `StageConfirmDialog.vue` 用 `<CollectingContentRenderer>` 替换内联逻辑

### Task 4.2：CleaningContentRenderer
- **文件**: [frontend/src/components/stage-renderers/CleaningContentRenderer.vue](file:///d:/project/trae_projects/scdc/frontend/src/components/stage-renderers/CleaningContentRenderer.vue)（**新建**）
- **Props**: `stageOutput: { cleaned_items, stats }`
- **UI**:
  - 顶部 stats 卡片（输入数 / 输出数 / 移除数）
  - 清洗后信源列表（每条带勾选框，勾上 = 加入 `removed_item_ids`）
  - 折叠区：阈值调整 (`min_content_length` slider, `language` select)
- **Emit**: `update:userEdits = { removed_item_ids, min_content_length, language }`

### Task 4.3：AnalyzingContentRenderer
- **文件**: [frontend/src/components/stage-renderers/AnalyzingContentRenderer.vue](file:///d:/project/trae_projects/scdc/frontend/src/components/stage-renderers/AnalyzingContentRenderer.vue)（**新建**）
- **Props**: `stageOutput: { insights, dimensions }`
- **UI**:
  - 维度标签条（chips）
  - 洞察卡片列表（每条带勾选框 + 标题 + 描述 + 证据）
  - 折叠区：补充自定义维度（tag input）
- **Emit**: `update:userEdits = { removed_insight_ids, custom_dimensions }`

### Task 4.4：ReportingContentRenderer
- **文件**: [frontend/src/components/stage-renderers/ReportingContentRenderer.vue](file:///d:/project/trae_projects/scdc/frontend/src/components/stage-renderers/ReportingContentRenderer.vue)（**新建**）
- **Props**: `stageOutput: { report, sections }`
- **UI**:
  - 左：报告 markdown 渲染（带"编辑"按钮）
  - 右：章节结构树（点章节 → 编辑面板）
  - 折叠区：增/删章节
- **Emit**: `update:userEdits = { edited_sections, removed_section_ids, appended_sections }`

---

## Phase 5：StageConfirmDialog 框架改造

### Task 5.1：动态内容区（4 个 renderer 切换）
- **文件**: [frontend/src/components/StageConfirmDialog.vue](file:///d:/project/trae_projects/scdc/frontend/src/components/StageConfirmDialog.vue)
- **改动**:
  - 顶部 import 4 个 renderer
  - 中间内容区用 `<component :is="...">` 动态渲染
  - 按 `ctx.stage` 选 renderer：
    ```vue
    <component
      :is="rendererFor(ctx.stage)"
      :stageOutput="ctx.stageOutput"
      v-model:userEdits="userEdits"
    />
    ```

### Task 5.2：关闭二次确认
- **文件**: 同上
- **改动**:
  - `<el-dialog>` 的 `:before-close` 拦截
  - 弹 `<el-popconfirm>` 或 `<el-message-box>` "确定离开？会接受当前结果"
  - 用户选"确定" → 等价 accept，调 `confirmStage` API
  - 用户选"取消" → 留在弹窗

### Task 5.3：跳过勾选
- **文件**: 同上 + [workflow.ts](file:///d:/project/trae_projects/scdc/frontend/src/stores/workflow.ts)
- **改动**:
  - 弹窗底部"接受"按钮旁加 `<el-checkbox v-model="skipRemaining">` "本次剩余阶段自动接受"
  - 点击"接受"时若勾选 → `store.setSkipRemaining(workflowId, true)`
  - store 的 `shouldAutoSkip` 决定下次 `stage_complete` 行为

### Task 5.4：SSE 监听器动态切换
- **文件**: [frontend/src/views/WorkflowView.vue](file:///d:/project/trae_projects/scdc/frontend/src/views/WorkflowView.vue) + [workflow store](file:///d:/project/trae_projects/scdc/frontend/src/stores/workflow.ts)
- **改动**:
  - 收到 `stage_complete` 事件时，根据 `next_stage` 关闭当前 EventSource，开新的
  - 新 SSE URL 模板：`/api/v1/workflow/${id}/stream-${stage}?token=${token}`
  - 接收 confirm 响应里的 `sse_url` 字段也支持（兼容性）

### Task 5.5：WorkflowView 集成
- **文件**: [frontend/src/views/WorkflowView.vue](file:///d:/project/trae_projects/scdc/frontend/src/views/WorkflowView.vue)
- **改动**:
  - 监听 4 个 stage 的 `awaiting_confirmation` 事件
  - 触发时调 `store.showConfirmDialog(ctx)`
  - 弹窗组件路径不变（`StageConfirmDialog`）

---

## Phase 6：测试

### Task 6.1：后端单元测试
- **文件**: [backend/tests/test_stage_runner_generalized.py](file:///d:/project/trae_projects/scdc/backend/tests/test_stage_runner_generalized.py)（**新建**）
- **覆盖**:
  - `run_stage_only_stream` 对 4 阶段 dispatch 正确
  - `collecting` 行为与现有 `run_collecting_only_stream` 一致
  - 状态机：accept → 下一阶段、reject → 重跑、skip → 等价 accept
  - 3 次 retry 上限（429）
  - skip 不计入重试

- **文件**: [backend/tests/test_user_edits_per_stage.py](file:///d:/project/trae_projects/scdc/backend/tests/test_user_edits_per_stage.py)（**新建**）
- **覆盖**:
  - 4 阶段 user_edits schema 解析
  - cleaning/analyzing/reporting 阶段的 user_edits 合并到下一阶段输入

### Task 6.2：后端集成测试
- **文件**: [backend/tests/test_cleaning_endpoint.py](file:///d:/project/trae_projects/scdc/backend/tests/test_cleaning_endpoint.py)（**新建**）
- **覆盖**:
  - 200 SSE 正常流（stage_start → progress → stage_complete）
  - 404 / 409 / 401 错误码

- 同上模式 `test_analyzing_endpoint.py` + `test_reporting_endpoint.py`（**新建**）

- **文件**: [backend/tests/test_confirm_skip.py](file:///d:/project/trae_projects/scdc/backend/tests/test_confirm_skip.py)（**新建**）
- **覆盖**:
  - skip 行为
  - skip 不增加 retry 计数
  - skip 后 stage_history 记录 decision='skip'

- **文件**: [backend/tests/test_workflow_status.py](file:///d:/project/trae_projects/scdc/backend/tests/test_workflow_status.py)（**新建**）
- **覆盖**:
  - status 端点返 stage_output + stage_state
  - 404 / 401

### Task 6.3：前端测试
- **文件**: [frontend/src/components/__tests__/StageConfirmDialog.spec.ts](file:///d:/project/trae_projects/scdc/frontend/src/components/__tests__/StageConfirmDialog.spec.ts)（**新建/更新**）
- **覆盖**:
  - 4 个 renderer 动态切换
  - 关闭二次确认
  - 跳过勾选
  - 4 个 decision 行为

---

## Phase 7：手工 E2E + commit

### Task 7.1：手工 E2E
- 启动后端 + 前端
- 跑一次完整工作流（4 阶段 + 4 弹窗）
- 验证 skip 模式
- 验证关闭二次确认
- 验证页面刷新恢复弹窗
- 验证 retry 3 次上限

### Task 7.2：commit
- 按 Spec 1 模式分 5-7 个 commit
- commit message 规范：`feat(spec2): Phase N ...`

---

## 风险预案

| 风险 | 触发条件 | 应对 |
|------|----------|------|
| 通用 runner 抽象遗漏 stage 特定逻辑 | 实施 Phase 1 时发现 CleanerAgent 输入/输出 schema 跟 CollectorAgent 差异大 | 在 dispatcher 里给每个 stage 单独写适配函数（不强行统一） |
| Spec 1 老测试 break | MAX_RETRY_PER_STAGE 从 5 改 3 | 同步改 `test_stage_confirmation.py` 中超 5 次的用例为超 3 次 |
| 4 个 renderer 开发量大 | Phase 4 估计要 4-6 小时 | 优先做 cleaning + analyzing（最常用），reporting 简化版先用只读 + 文字反馈兜底 |
| 前端 SSE 动态切换出问题 | 实施 Phase 5.4 时发现 EventSource 关闭/重开有竞态 | 引入 in-flight flag，confirm 响应回来前不发新 SSE |
