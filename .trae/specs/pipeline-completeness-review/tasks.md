# 全流程验收与完整性增强 — 任务列表

# Tasks
- [x] Task 1: 修复 OrchestratorAgent 参数传递，确保 dimensions/include_charts/source_contents 正确传递到下游 Agent
  - [x] SubTask 1.1: 修改 `orchestrator.py` 第 77 行 `AnalyzerInput` 创建，传入 `dimensions=input_data.dimensions`
  - [x] SubTask 1.2: 修改 `orchestrator.py` 第 84 行 `ReporterInput` 创建，传入 `dimensions=input_data.dimensions` 和 `source_contents`（从 `cln_out.cleaned_items` 构建）
- [x] Task 2: 统一工作流引擎 — 让 `workflow.py` 复用 `OrchestratorAgent`
  - [x] SubTask 2.1: 创建 `asyncio.Queue` + `sse_callback` 桥接 OrchestratorAgent 状态变更到 SSE yield
  - [x] SubTask 2.2: 重构 `run_workflow_stream`，使用 `OrchestratorAgent(state_callback=...)` + `execute()` 替代手动调用
  - [x] SubTask 2.3: 删除 `workflow.py` 中 `_run_collect/_run_clean/_run_analyze/_run_report` 四个冗余方法
  - [x] SubTask 2.4: 在 SSE `completed` 事件中附带 `collected_count`/`cleaned_count`/`insight_count` 统计
- [x] Task 3: 工作流持久化
  - [x] SubTask 3.1: 创建 `WorkflowRun` SQLAlchemy 模型（id, workflow_id, topic, status, current_stage, stages_json, result_json, error, created_at, updated_at）
  - [x] SubTask 3.2: 在 `main.py` lifespan 中添加 `CREATE TABLE IF NOT EXISTS workflow_runs` DDL
  - [x] SubTask 3.3: 修改 `WorkflowService`: `create_workflow` 写入 DB，`get_workflow` 从 DB 读取，`run_workflow_stream` 每个阶段完成后更新 DB
  - [x] SubTask 3.4: 修改 `get_history()` 从 `workflow_runs` 表读取
- [x] Task 4: 自动报告入库
  - [x] SubTask 4.1: 在 `run_workflow_stream` 的 `completed` 事件前，调用 `ReportService.create_from_workflow` 自动入库
  - [x] SubTask 4.2: 在 SSE `completed` 事件中附带 `report_id`，前端接收后缓存
- [x] Task 5: 端到端集成测试脚本
  - [x] SubTask 5.1: 创建 `tests/e2e/test_pipeline.py`，执行完整流程并验证各阶段输出非空
  - [x] SubTask 5.2: 添加测试脚本，可一键执行
- [x] Task 6: 前端阶段统计展示优化
  - [x] SubTask 6.1: 在 `WorkflowView.vue` 的 SSE 事件处理中解析统计数据
  - [x] SubTask 6.2: 在消息气泡中展示每个阶段的统计（采集 N 条、清洗后 N 条、生成 N 个洞察）

# Task Dependencies
- [Task 1] 无依赖，可立即开始
- [Task 2] 依赖 [Task 1]（需先修复 OrchestratorAgent 参数传递）
- [Task 3] 无依赖，可与 Task 1 并行
- [Task 4] 依赖 [Task 2]（需先统一工作流引擎）
- [Task 5] 无依赖，可与 Task 1/3 并行
- [Task 6] 依赖 [Task 2]（需先统一工作流引擎，拿到统计数据）