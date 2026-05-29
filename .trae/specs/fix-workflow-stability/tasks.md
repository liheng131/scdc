# Tasks

- [x] Task 1: 缩短 LLM 调用超时，加速降级
  - 修改 `backend/app/agents/analyzer.py`：
    - `_call_llm` 的 `timeout` 参数从 300 改为 60
    - `@retry` 的 `stop_after_attempt` 从 2 改为 1（降级只尝试 1 次）
    - `retry_if_exception_type` 增加 `httpx.ConnectError` 和 `httpx.ConnectTimeout`
  - 修改 `backend/app/agents/reporter.py`：同 analyzer.py 的三处修改
  - **验证**: LLM 不可达时，analyzing+reporting 总耗时不超过 3 分钟 ✓

- [x] Task 2: 确保 Docker 构建完整性
  - 检查 `backend/requirements.txt` 是否包含 `python-pptx` 和 `httpx` ✓
  - 检查 `backend/Dockerfile` 是否正确安装 `requirements.txt`（移除 --no-deps） ✓
  - **验证**: `docker compose build backend` 无错误，python-pptx 1.0.2 已安装 ✓

- [x] Task 3: 前端 SSE 长时间无进度提示
  - 修改 `frontend/src/views/WorkflowView.vue`：
    - 在 SSE 连接建立后启动一个 60s 计时器 ✓
    - 如果 60s 内未收到任何 `stage_complete` 或 `completed` 事件 ✓
    - 在消息区域顶部显示提示"当前阶段可能耗时较久，请耐心等待..."（使用 ElAlert type="info"） ✓
    - 收到下一个 SSE 事件后自动清除提示 ✓
    - SSE 断连时清除计时器 ✓
  - **验证**: 工作流执行超过 60s 无进度时前端显示提示 ✓

- [x] Task 4: 重新构建并部署 Docker
  - 执行 `docker compose build --no-cache backend frontend` ✓
  - 执行 `docker compose up -d backend frontend` ✓
  - 查看后端日志确认 `migrate_task_id_column()` 执行成功 ✓
  - **验证**: 所有功能端到端可用 ✓

# Task Dependencies
- Task 4 依赖 Task 1、2、3 全部完成 ✓
- Task 1、2、3 可并行执行