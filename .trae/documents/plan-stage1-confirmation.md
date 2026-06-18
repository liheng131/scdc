# Spec 1 实现计划：数据采集阶段 Human-in-the-Loop 确认

> 创建日期: 2026-06-10
> 设计文档: [2026-06-10-stage1-confirmation-design.md](file:///d:/project/trae_projects/scdc/docs/superpowers/specs/2026-06-10-stage1-confirmation-design.md)
> 总工作量: 7 个文件改动 + 2 个测试文件 + 1 个 DB 迁移

## 任务清单

### Phase 1: 后端基础（DB + Model + Schema）

#### Task 1.1: 添加 stage_state / stage_output / stage_history 字段
- **文件**: [backend/app/models/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/models/workflow.py)
- **改动**:
  - 加 `StageState` 枚举类（4 个值：running / awaiting_confirmation / completed / failed）
  - 在 `WorkflowRun` ORM 模型上加 3 个字段：
    - `stage_state: Mapped[str]` (String 32, default='running')
    - `stage_output: Mapped[Optional[dict]]` (JSON, nullable=True)
    - `stage_history: Mapped[Optional[list]]` (JSON, nullable=True, default=list)
- **验证**: `python -c "from app.models.workflow import WorkflowRun; print(WorkflowRun.__table__.columns.keys())"` 应包含 3 个新列
- **风险**: 现有数据 `stage_state` 默认 'running'，向后兼容

#### Task 1.2: 创建 Alembic 迁移
- **文件**: `backend/alembic/versions/xxxx_add_stage_fields.py` (新建)
- **改动**:
  - `op.add_column('workflow_runs', sa.Column('stage_state', sa.String(32), server_default='running', nullable=False))`
  - `op.add_column('workflow_runs', sa.Column('stage_output', sa.JSON, nullable=True))`
  - `op.add_column('workflow_runs', sa.Column('stage_history', sa.JSON, nullable=True))`
- **验证**: 跑 `alembic upgrade head` 不报错；用 `psql` 检查字段已存在

#### Task 1.3: 新增 Schema
- **文件**: [backend/app/schemas/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/schemas/workflow.py)
- **改动**:
  ```python
  class ConfirmStageRequest(BaseModel):
      decision: Literal["accept", "reject"]
      user_edits: Optional[Dict[str, Any]] = None
      user_feedback: Optional[str] = None

  class WorkflowStatusResponse(BaseModel):
      run_id: str
      stage: str
      stage_state: str
      stage_output: Optional[Dict[str, Any]] = None
      stage_history: Optional[List[Dict[str, Any]]] = None
  ```
- **验证**: `python -c "from app.schemas.workflow import ConfirmStageRequest, WorkflowStatusResponse; print('ok')"`

---

### Phase 2: 后端业务逻辑

#### Task 2.1: WorkflowService 新增 confirm_stage 方法
- **文件**: [backend/app/services/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/services/workflow.py)
- **新增方法**:
  ```python
  async def confirm_stage(
      self, session, run_id: str, payload: ConfirmStageRequest
  ) -> WorkflowRun:
      """处理用户确认：accept 进入下一阶段，reject 重跑当前阶段。
      包含重试次数检查（> 5 次返回 429）和并发锁（仅 awaiting_confirmation 可 confirm）。"""
  ```
- **关键逻辑**:
  - 查 workflow_run，404 if not found
  - 状态校验：必须 stage_state == 'awaiting_confirmation'，否则 409
  - 重试次数 = len(stage_history)，> 5 → 429
  - 把当前 (stage, output, decision, user_edits, user_feedback) push 到 stage_history
  - decision == 'accept'：
    - 推进到下一阶段（collecting → cleaning）
    - 触发新的 SSE 流生成器
  - decision == 'reject'：
    - 当前阶段标记为 running
    - 合并 user_edits 到 topic
    - 重新启动当前阶段
- **验证**: 单元测试覆盖各分支

#### Task 2.2: Orchestrator 改造 — collecting 阶段写 stage_output
- **文件**: [backend/app/agents/orchestrator.py](file:///d:/project/trae_projects/scdc/backend/app/agents/orchestrator.py)
- **改动**:
  - collecting 阶段 collector.execute() 完成后，把输出（搜索结果 source 列表）写入 `workflow_run.stage_output`
  - 设 `workflow_run.stage_state = 'awaiting_confirmation'`
  - 提交数据库
  - SSE 流中发 `{"event": "stage_complete", "stage": "collecting", "output": {...}}` 事件
  - SSE 生成器正常结束（不再自动进入 cleaning）
- **验证**: 跑一次工作流，检查 DB 中 `stage_output` 字段有内容，`stage_state='awaiting_confirmation'`

#### Task 2.3: 新增 API 端点
- **文件**: [backend/app/api/routes/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/workflow.py)
- **新增端点**:
  ```python
  @router.post("/workflow/{run_id}/confirm", status_code=202)
  async def confirm_stage_endpoint(run_id: str, payload: ConfirmStageRequest, ...):
      run = await workflow_service.confirm_stage(session, run_id, payload)
      return {
          "run_id": run.id,
          "stage": run.stage,
          "stage_state": run.stage_state,
          "sse_url": f"/api/v1/workflow/{run_id}/stream"
      }

  @router.get("/workflow/{run_id}/status")
  async def get_workflow_status(run_id: str, ...):
      run = await workflow_service.get_run(session, run_id)
      return WorkflowStatusResponse(...)
  ```
- **验证**: 用 curl 测 accept / reject 路径，409 / 429 错误码

#### Task 2.4: 修改 collect 端点
- **文件**: [backend/app/api/routes/workflow.py](file:///d:/project/trae_projects/scdc/backend/app/api/routes/workflow.py)
- **改动**:
  - 创建 `workflow_run` 时设 `stage_state='running'`
  - SSE 流结束条件从"阶段完成"改为"阶段完成 + 状态切换为 awaiting_confirmation"
  - SSE 事件新增 `{"event": "stage_complete", ...}`
- **验证**: 端到端测试

---

### Phase 3: 前端集成

#### Task 3.1: 新建 StageConfirmDialog 组件
- **文件**: `frontend/src/components/workflow/StageConfirmDialog.vue` (新建)
- **结构**:
  - `<el-dialog>` 包裹
  - Props: `visible`, `stage`, `stageOutput`, `loading`
  - Emit: `confirm({decision, userEdits, userFeedback})`, `cancel`
  - 内部 state: `userEdits = { extra_urls: [], extra_keywords: [] }`, `userFeedback = ''`
  - UI 区域：源列表展示 / 添加 URL 按钮 / 添加关键词按钮 / 文字反馈 textarea / 接受拒绝按钮
  - 针对 stage='collecting' 显示源列表；其他 stage 暂显示 "通用预览"
- **验证**: 组件 snapshot 测试或视觉验证

#### Task 3.2: Pinia store 新增 confirm action
- **文件**: `frontend/src/stores/workflow.ts` (或 .js)
- **新增**:
  ```typescript
  async confirm(runId: string, payload: ConfirmPayload): Promise<void> {
      const res = await fetch(`/api/v1/workflow/${runId}/confirm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(`Confirm failed: ${res.status}`);
      const data = await res.json();
      // 启动新 SSE 流
      this.startSSE(data.sse_url);
  }
  ```
- **验证**: 单元测试或 E2E 测试

#### Task 3.3: WorkflowView 集成弹窗
- **文件**: `frontend/src/views/WorkflowView.vue`
- **改动**:
  - 监听 SSE `stage_complete` 事件
  - 触发时设 `dialogVisible = true`
  - `dialog.confirm` 回调调用 `store.confirm()`
  - `dialog.cancel` 关闭弹窗（不操作）
- **验证**: E2E 手工测试

---

### Phase 4: 测试

#### Task 4.1: 单元测试 - 状态机
- **文件**: `backend/tests/test_workflow_state_transitions.py` (新建)
- **用例**:
  - 初始状态 running
  - collecting 完成后切换 awaiting_confirmation
  - accept 后切换到 cleaning + running
  - reject 后切换到 collecting + running
  - 重试次数累加
  - 重复 confirm 返回 409
  - 重试 > 5 返回 429

#### Task 4.2: 集成测试 - confirm 端点
- **文件**: `backend/tests/test_workflow_confirm.py` (新建)
- **用例**:
  - POST /workflow/{id}/confirm 路径覆盖
  - 200 正常路径
  - 404 不存在
  - 409 重复
  - 429 重试过多
  - 422 字段缺失

#### Task 4.3: E2E 测试 - 完整 happy path + 重试 path
- **文件**: `backend/tests/test_e2e_stage1_confirmation.py` (新建)
- **用例**:
  - happy path: 启动 → 采集完成 → confirm accept → 进入 cleaning
  - retry path: 启动 → 采集完成 → confirm reject → 重新采集 → confirm accept → 进入 cleaning
  - edit path: 启动 → 采集完成 → confirm reject+user_edits → 重新采集（合并输入）→ accept

---

### Phase 5: 验证与文档

#### Task 5.1: 跑全部测试
- `cd backend && python -m pytest tests/test_workflow_state_transitions.py tests/test_workflow_confirm.py tests/test_e2e_stage1_confirmation.py -v`
- 跑回归：`python -m pytest tests/ -v`
- 期望：所有测试通过，旧测试无 regression

#### Task 5.2: 手工验证清单
- 启动"2025年AI芯片市场"工作流
- 采集完成弹窗出现
- 添加 1 个 URL
- 点击拒绝重试
- 新一轮采集完成，弹窗再次出现
- 点击接受
- 进入数据清洗（验证 stage_history 记录）

#### Task 5.3: Commit + 文档更新
- 提交所有改动
- 更新 [docs/architecture.md](file:///d:/project/trae_projects/scdc/docs/architecture.md)（如果存在）增加新架构图

---

## 风险与依赖

| 风险 | 缓解 |
|------|------|
| Alembic 迁移在已有 DB 上失败 | 写手动 SQL 脚本作为兜底 |
| SSE 重订阅丢消息 | SSE 端点先发 `stage_state` 状态，前端据此判断 |
| 前端弹窗与现有 UI 冲突 | 选用 Element Plus el-dialog，避免引入新 UI 库 |
| 旧工作流 run 没有新字段 | DB 迁移加 server_default='running'，旧 run 视为 running |

## 依赖项

- 后端：现有 WorkflowService / OrchestratorAgent / SSE 流机制
- 前端：Element Plus / Pinia / 现有 SSE 客户端
- DB：现有 workflow_runs 表

## 后续 4 个 Spec 衔接

完成后留出 4 个 extension point：
1. `<StageConfirmDialog>` 组件加 stage='cleaning' 分支
2. confirm 端点支持 stage='cleaning' 路径
3. 框架推荐选择 UI 嵌入 cleaning 弹窗
4. 后续 Spec 直接复制此模式

## 工作量估算

- Phase 1: 0.5 天
- Phase 2: 1.5 天
- Phase 3: 1 天
- Phase 4: 0.5 天
- Phase 5: 0.5 天
- **总计: 4 天**
