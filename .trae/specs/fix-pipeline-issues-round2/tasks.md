# 全流程问题修复（第二轮）— 任务列表

# Tasks
- [x] Task 1: Schema 扩展 — 为 CollectorOutput/AnalyzerOutput/ReporterOutput/OrchestratorOutput 新增降级标记、警告、部分结果和图表图片字段
  - [x] SubTask 1.1: 修改 `backend/app/schemas/agent.py`，CollectorOutput 新增 `warning: Optional[str] = None`
  - [x] SubTask 1.2: 修改 `backend/app/schemas/agent.py`，AnalyzerOutput 新增 `degraded: bool = False`
  - [x] SubTask 1.3: 修改 `backend/app/schemas/agent.py`，ReporterOutput 新增 `degraded: bool = False` 和 `chart_images: List[Dict[str, str]] = []`
  - [x] SubTask 1.4: 修改 `backend/app/schemas/agent.py`，OrchestratorOutput 新增 `partial_results: Optional[Dict[str, Any]] = None`

- [x] Task 2: 修复 SerpAPI 错误传递 — CollectorAgent 区分 API 失败和空结果
  - [x] SubTask 2.1: 修改 `collector.py`，当 `search_resp.success=False` 时返回 `success=False` 并带 error
  - [x] SubTask 2.2: 修改 `orchestrator.py`，collecting 阶段失败时中止流水线并返回错误

- [x] Task 3: 修复降级处理标记 — AnalyzerAgent 和 ReporterAgent 降级时标记 degraded
  - [x] SubTask 3.1: 修改 `analyzer.py`，`_rule_based_degradation` 返回 `degraded=True`
  - [x] SubTask 3.2: 修改 `reporter.py`，模板报告和 LLM 失败时返回 `degraded=True`

- [x] Task 4: 图表图片渲染 — 将 ECharts 配置渲染为 PNG 并嵌入报告
  - [x] SubTask 4.1: 在 `reporter.py` 中添加 `_render_chart_to_base64()` 方法，使用 `pyecharts` 或 `matplotlib` 渲染图表为 PNG base64
  - [x] SubTask 4.2: 在 `ReporterAgent.execute()` 中调用渲染，将 base64 图片存入 `chart_images` 字段
  - [x] SubTask 4.3: 在报告 markdown 中嵌入图表图片引用 `![图表名](data:image/png;base64,...)`
  - [x] SubTask 4.4: 在 `report.py` 的 `generate_docx()` 中嵌入图表图片
  - [x] SubTask 4.5: 在 `report.py` 的 `generate_pdf()` 中嵌入图表图片
  - [x] SubTask 4.6: 在 `report.py` 的 `generate_pptx()` 中嵌入图表图片

- [x] Task 5: 多类型图表支持 — ReporterAgent 生成饼图+柱状图+折线图
  - [x] SubTask 5.1: 修改 `reporter.py` 的 `_generate_chart_configs()`，根据维度数生成柱状图配置
  - [x] SubTask 5.2: 当 source_contents 包含时间信息时生成折线图配置

- [x] Task 6: 导出操作同步入库 — 导出时自动将报告存入 reports 表并更新向量库
  - [x] SubTask 6.1: 修改 `report.py` 的 `export_report()`，导出前确保报告已入库（若无则先创建）
  - [x] SubTask 6.2: 在导出完成后异步触发向量库重索引（调用 `_embed_and_store`）

- [x] Task 7: 流水线部分结果保留 — 失败时保留中间结果
  - [x] SubTask 7.1: 修改 `orchestrator.py`，失败时将已收集的阶段结果写入 `partial_results`
  - [x] SubTask 7.2: 修改 `workflow.py`，在 SSE 错误事件中附带 `partial_results`

- [x] Task 8: 向量维度动态获取
  - [x] SubTask 8.1: 修改 `main.py`，从 EmbeddingService 获取实际向量维度替代硬编码 768

- [x] Task 9: 前端适配 — 降级警告、中间结果展示、图表渲染
  - [x] SubTask 9.1: 修改 `WorkflowView.vue`，接收并展示 `degraded` 警告信息
  - [x] SubTask 9.2: 修改 `WorkflowView.vue`，失败时展示部分中间结果
  - [x] SubTask 9.3: 修改 `WorkflowView.vue`，在报告中渲染内嵌的 base64 图表图片
  - [x] SubTask 9.4: 修改 `ReportsView.vue`，预览报告时渲染内嵌图表图片

# Task Dependencies
- [Task 1] 无依赖，优先执行（Schema 变更是所有下游任务的前提）
- [Task 2] 依赖 [Task 1]（需要 warning 字段）
- [Task 3] 依赖 [Task 1]（需要 degraded 字段）
- [Task 4] 依赖 [Task 1]（需要 chart_images 字段）
- [Task 5] 依赖 [Task 4]（共用图表渲染基础设施）
- [Task 6] 无依赖，可与 Task 2-4 并行
- [Task 7] 依赖 [Task 1]（需要 partial_results 字段）
- [Task 8] 无依赖，可独立执行
- [Task 9] 依赖 [Task 1-8]（需要后端所有变更完成）