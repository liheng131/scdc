# Tasks

- [x] Task 1: 修改导出接口认证方式
  - 修改 `backend/app/api/routes/reports.py` 的 `export_report` 函数
  - 将依赖 `get_current_active_user` 改为 `get_current_active_user_sse`
  - 导入 `get_current_active_user_sse`（如果尚未导入）
  - **验证**: 代码修改正确，`get_current_active_user_sse` 支持 `?token=xxx` 查询参数 ✓

- [x] Task 2: 重建后端 Docker 并重启
  - 执行 `docker compose build backend`（无需 --no-cache，代码已缓存）✓
  - 执行 `docker compose up -d backend` ✓
  - 确认后端启动成功 ✓

- [x] Task 3: 验证导出接口
  - 使用 curl/PowerShell 模拟 `?token=xxx` 方式调用导出接口 ✓
  - 验证 pdf、docx、pptx 三种格式都能正常下载（不再返回 401）✓

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 2
