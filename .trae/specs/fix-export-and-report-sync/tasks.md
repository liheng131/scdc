# Tasks

- [x] Task 1: 数据库列类型迁移（导出失败根因）
  - 在 `backend/app/core/db.py` 新增 `async def migrate_task_id_column(engine)` 函数，检测 reports 表 task_id 列类型，如果为 integer 则执行 `ALTER TABLE reports ALTER COLUMN task_id TYPE VARCHAR(50)`
  - 在 `backend/main.py` 启动时（`lifespan` 函数中）调用此迁移函数
  - **验证**: 后端重启后 reports 表 task_id 列类型为 varchar(50)

- [x] Task 2: 增强 _save_report 日志与错误处理
  - 修改 `backend/app/services/workflow.py` 的 `_save_report` 方法：
    - 在方法开始处记录 INFO 日志 "开始保存报告 workflow_id=..."
    - 成功时记录 INFO 日志 "报告保存成功 id=X workflow_id=..."
    - 失败时使用 `logger.error(f"保存报告失败 workflow_id=...: {e}", exc_info=True)` 记录完整异常堆栈
    - 增加 `summary` 字段（截取 report_markdown 前 200 字符作为摘要）
    - 增加重试机制（最多重试 2 次，间隔 1 秒）
  - **验证**: 后端日志中能看到保存报告的详细日志

- [x] Task 3: 前端导出增加重试逻辑
  - 修改 `frontend/src/views/WorkflowView.vue` 的 `handleExportReport` 方法：
    - 对非 md 格式导出，如果首次查询 reportId 为空，则最多重试 3 次，每次间隔 1 秒
    - 重试过程中显示 loading 状态提示
    - 所有重试失败后提示用户稍后重试
  - **验证**: 工作流完成后点击导出，能正确查询到报告并下载文件

- [x] Task 4: 验证智能报告页面能展示工作流产出的报告
  - 确认 ReportsView.vue 的 fetchReports 能正确加载 task_id 为字符串的报告
  - 确认 ReportOut 的 task_id 字段正确序列化
  - **验证**: 执行工作流后，智能报告页面能自动展示对应报告

# Task Dependencies
- Task 2 和 Task 3 可并行执行
- Task 4 依赖 Task 1 完成
- Task 1 是其他任务的前置条件