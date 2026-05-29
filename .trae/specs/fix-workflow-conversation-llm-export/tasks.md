# Tasks

- [x] Task 1: 修复 Report 模型 task_id 类型不匹配（导出失败根因）
  - 修改 `backend/app/models/report.py`：将 `task_id` 从 `Mapped[int]` ForeignKey 改为 `Mapped[Optional[str]]`（与 Task 表解耦，兼容字符串 workflow_id）
  - 修改 `backend/app/schemas/report.py`：`ReportCreate.task_id` 改为 `Optional[str]`，`ReportOut.task_id` 改为 `Optional[str]`
  - 修改 `backend/app/services/workflow.py`：`_save_report()` 正确传入字符串 workflow_id
  - 修改 `backend/app/api/routes/reports.py`：`task_id` 查询参数改为 `Optional[str]`
  - 修改 `backend/app/services/report.py`：`list_reports` 的 `task_id` 参数改为 `Optional[str]`
  - 修改 `frontend/src/api/services/reports.ts`：`task_id` 参数类型改为 `string`
  - 修改 `frontend/src/views/WorkflowView.vue`：`handleExportReport` 移除 `as unknown as number` 强制转换
  - 修改 `frontend/src/views/ReportsView.vue`：报告详情展示兼容 task_id 为字符串
  - **验证**: 执行工作流后导出报告，文件下载成功

- [x] Task 2: 新增"新建对话"按钮
  - 在 `frontend/src/stores/workflow.ts` 新增 `resetActiveConversation` 方法，清除活跃会话并回到空状态
  - 在 `frontend/src/views/WorkflowView.vue` 聊天头部区域添加"新建对话"按钮（el-button）
  - 如果当前有工作流正在执行，先弹确认框提示用户，确认后调用 `clearEventSource` 停止 SSE
  - **验证**: 点击新建对话后界面回到空状态；有活跃工作流时弹出确认框

- [x] Task 3: LLM 服务地址纳入 runtime_config 管理
  - 修改 `backend/app/core/runtime_config.py`：`_DEFAULTS` 新增 `llm_base_url` 配置项，默认使用 `settings.ollama_base_url`
  - 修改 `backend/app/agents/analyzer.py`：`_call_llm` 中的 LLM URL 改为从 `rumtime_config.get("llm_base_url")` 读取
  - 修改 `backend/app/agents/reporter.py`：`_call_llm` 中的 LLM URL 改为从 `rumtime_config.get("llm_base_url")` 读取
  - 在 `frontend/src/views/SettingsView.vue` 系统设置页新增"LLM 服务地址"输入框
  - 修改 `frontend/src/views/SettingsView.vue` 的 `handleSave`，增加 `llm_base_url` 字段
  - **验证**: 在设置页修改 LLM 服务地址并保存，后端 runtime_config.json 正确更新

- [x] Task 4: LLM 健康检查与测试连接
  - 在 `backend/app/api/routes/settings.py` 新增 `GET /llm-health` 端点，向 LLM 服务发送最小请求验证连通性并返回可用模型列表
  - 在 `frontend/src/api/services/settings.ts` 新增 `checkLlmHealth` API 方法
  - 在 `frontend/src/views/SettingsView.vue` LLM 服务地址旁新增"测试连接"按钮，点击后调用健康检查 API 并显示结果（成功/失败/加载中）
  - **验证**: 点击测试连接按钮，LLM 可用时显示成功提示，不可用时显示失败提示

# Task Dependencies
- Task 3 和 Task 4 彼此独立，但都依赖 runtime_config 扩展
- Task 4 依赖于 Task 3 中的 runtime_config llm_base_url 字段新增
- Task 1 和 Task 2 彼此独立，可并行执行