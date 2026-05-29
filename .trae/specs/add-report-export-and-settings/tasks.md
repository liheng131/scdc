# Tasks

- [x] Task 1: 后端 PPT 导出支持
  - 在 `ReportService` 中新增 `generate_pptx()` 方法，使用 python-pptx 库将 Markdown 报告转换为 PPTX 文件（标题映射为幻灯片标题，段落映射为内容）
  - 在 `export_report()` 方法中添加 `pptx` 格式分支
  - 在 `requirements.txt` 中添加 python-pptx 依赖
  - **验证**: 调用 `GET /api/v1/reports/{id}/export?fmt=pptx` 返回 `.pptx` 文件

- [x] Task 2: 工作流完成后自动报告入库
  - 修改 `WorkflowService.run_workflow_stream()`，在 SSE completed 事件发送后，异步调用 `ReportService.create_report()` 将报告写入数据库（title=topic，content_markdown=report_markdown）
  - 确保 workflow_service 能获取到 DB session

- [x] Task 3: 后端运行时配置 API
  - 新建 `backend/app/api/routes/settings.py`，提供 `GET /api/v1/settings` 和 `PUT /api/v1/settings` 接口
  - 配置项存储使用简单的内存字典 + 持久化 JSON 文件（或直接用 SQLite/Postgres 表），支持读取和更新 llm_provider / llm_api_key / default_model / temperature / max_tokens
  - 修改 `app/core/config.py`，使 Agent 初始化时从运行时配置源读取而非仅依赖环境变量

- [x] Task 4: 前端报告多格式导出按钮
  - 修改 `WorkflowView.vue` 报告生成后的操作区域，将单个"导出 Markdown"按钮替换为格式选择下拉菜单（Markdown / DOCX / PDF / PPTX），用户选择格式后触发下载
  - 调用 `reportsApi.exportReportUrl(id, fmt)` 触发下载

- [x] Task 5: 前端智能报告页面
  - 新建 `frontend/src/views/ReportsView.vue`（智能报告页面），展示报告列表（表格或卡片），支持分页、关键词搜索
  - 每条报告支持：预览（弹窗渲染 Markdown）、编辑标题（内联编辑）、删除（确认后调用 API）、多格式导出
  - 新增 `frontend/src/api/services/settings.ts` 前端 API 服务（如尚不存在）

- [x] Task 6: 前端路由与导航更新
  - 修改 `router/index.ts`：将 `/reports` 从 `redirect: '/workflow'` 改为指向新的 `ReportsView.vue`
  - 修改 `MainLayout.vue`：在侧边栏「大纲模板」与「系统设置」之间新增"智能报告"菜单项

- [x] Task 7: 前端系统设置页面对接后端
  - 改造 `SettingsView.vue`：页面加载时调用 `GET /api/v1/settings` 获取当前配置填充表单
  - 点击保存时调用 `PUT /api/v1/settings` 提交修改，保存成功后提示用户

# Task Dependencies
- Task 4 依赖 Task 1（前端导出需要后端 PPT 接口就绪）
- Task 5 依赖 Task 2（智能报告页面展示的报告来自自动入库）
- Task 6 可与 Task 5 并行
- Task 7 依赖 Task 3（前端设置页需要后端配置 API）
- Task 1、Task 2、Task 3 为后端任务，可并行开发