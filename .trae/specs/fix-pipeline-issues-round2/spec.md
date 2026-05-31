# 全流程问题修复（第二轮）Spec

## Why

首轮全流程验收修复了参数传递、工作流统一、持久化等基础问题。本轮深入审查发现仍存在 8 个关键缺陷：导出不入库导致"智能报告"页面不更新、报告未实现图文结合、降级处理无用户感知、SerpAPI 失败被当作正常空结果、流水线失败无中间结果保留、向量维度硬编码、导出后向量库未重索引、图表类型单一。这些问题直接影响核心用户体验和系统可靠性。

## What Changes

- **修复** 导出操作同步入库 — 用户点击导出后，导出的文档自动出现在"智能报告"页面
- **新增** 图表图片渲染 — 将 ECharts 配置渲染为 PNG 图片并嵌入报告 markdown 和导出文档
- **新增** 降级处理标记 — AnalyzerAgent 和 ReporterAgent 降级时显式标记 `degraded: true`，前端展示警告
- **修复** SerpAPI 错误传递 — 区分"搜索无结果"和"API 调用失败"
- **新增** 流水线部分结果保留 — 后期阶段失败时保留前期采集/清洗/分析结果
- **修复** 向量维度动态获取 — 从 EmbeddingService 获取实际维度，不再硬编码 768
- **新增** 导出后向量库重索引 — 导出的文档内容重新分块并写入向量数据库
- **新增** 多类型图表支持 — ReporterAgent 根据维度数和数据特征生成饼图+柱状图+趋势图

## Impact

- Affected specs: `pipeline-completeness-review`, `fix-export-and-report-sync`
- Affected code: `backend/app/agents/collector.py`, `backend/app/agents/analyzer.py`, `backend/app/agents/reporter.py`, `backend/app/agents/orchestrator.py`, `backend/app/services/report.py`, `backend/app/services/embedding.py`, `backend/app/api/routes/reports.py`, `backend/app/api/routes/export.py`, `backend/app/main.py`, `frontend/src/views/ReportsView.vue`, `frontend/src/views/WorkflowView.vue`

## ADDED Requirements

### Requirement: 导出操作同步入库
系统 SHALL 在用户点击导出报告时，将导出的报告文档自动保存到 `reports` 表，使其出现在"智能报告"页面。

#### Scenario: 用户在智能报告页导出文档
- **WHEN** 用户点击某个报告的"导出"按钮并选择格式
- **THEN** 文件正常下载，同时该报告（若尚未入库）自动写入 `reports` 表
- **THEN** "智能报告"页面在用户刷新后可看到该报告

#### Scenario: 用户在 workflow 结果页导出文档
- **WHEN** 用户在 workflow 对话页面点击导出
- **THEN** 报告自动入库，"智能报告"页面可查到

### Requirement: 图表图片渲染与嵌入
系统 SHALL 将 ReporterAgent 生成的 ECharts 图表配置渲染为 PNG 图片，嵌入报告的 markdown 内容和导出文档中。

#### Scenario: 报告生成时自动渲染图表
- **WHEN** ReporterAgent 生成报告且 `include_charts=True`
- **THEN** 图表配置被渲染为 base64 PNG 图片
- **THEN** markdown 报告中包含 `![图表](data:image/png;base64,...)` 格式的图片引用
- **THEN** 导出 DOCX/PDF/PPTX 时图表图片嵌入文档中

### Requirement: 降级处理显式标记
系统 SHALL 在 LLM 不可用导致降级处理时，在 AnalyzerOutput 和 ReporterOutput 中显式标记，并在前端展示降级警告。

#### Scenario: AnalyzerAgent LLM 调用失败
- **WHEN** AnalyzerAgent 的 `_call_llm` 抛出异常
- **THEN** 返回的 `AnalyzerOutput` 中 `degraded=True`
- **THEN** 前端 workflow 结果中显示"AI 分析服务暂不可用，当前展示基于规则的分析结果"

#### Scenario: ReporterAgent LLM 调用失败
- **WHEN** ReporterAgent 的 `_call_llm` 抛出异常或返回内容过短
- **THEN** 返回的 `ReporterOutput` 中 `degraded=True`
- **THEN** 前端 workflow 结果中显示"报告生成服务暂不可用，当前展示模板化报告"

### Requirement: SerpAPI 错误与空结果区分
系统 SHALL 区分 SerpAPI 搜索的三种状态：成功有结果、成功无结果、调用失败。

#### Scenario: SerpAPI 调用失败
- **WHEN** SerpAPI 返回 `success=False` 或有异常
- **THEN** CollectorOutput 中 `success=False` 并携带 `error` 信息
- **THEN** OrchestratorAgent 接收到失败后中止流水线并报告错误

#### Scenario: SerpAPI 返回空结果
- **WHEN** SerpAPI 返回 `success=True` 但 `results` 为空
- **THEN** CollectorOutput 中 `success=True`，`items=[]`，`warning="no_results"`
- **THEN** 流水线继续执行但 AnalyzerAgent 收到空数据时给出明确提示

### Requirement: 流水线部分结果保留
系统 SHALL 在流水线后期阶段失败时，将前期阶段已成功产出的中间结果写入 workflow state，供用户查看。

#### Scenario: 报告阶段失败
- **WHEN** OrchestratorAgent 在 reporting 阶段抛出异常
- **THEN** workflow result 中包含 `partial_results` 字段，含 collected_items/cleaned_items/analyzer_output
- **THEN** 前端展示"报告生成失败，但数据采集和 AI 分析已完成，可查看中间结果"

### Requirement: 向量维度动态获取
系统 SHALL 从 EmbeddingService 的实际输出中获取向量维度，而非硬编码。

#### Scenario: 初始化向量集合
- **WHEN** 系统启动时初始化 Milvus 集合
- **THEN** 通过 EmbeddingService 对一条测试文本编码，获取实际向量维度
- **THEN** 使用该维度创建向量集合

### Requirement: 导出后向量库重索引
系统 SHALL 在用户导出报告或手动上传报告后，将文档内容分块写入向量数据库，供后续 RAG 检索使用。

#### Scenario: 用户上传报告到智能报告页
- **WHEN** 用户在"智能报告"页面上传 PDF/DOCX/MD 文件
- **THEN** 文件内容被解析并写入 reports 表
- **THEN** 内容自动分块并嵌入向量数据库（已实现）

#### Scenario: 工作流完成后自动入库
- **WHEN** 工作流完成并自动创建报告
- **THEN** 报告内容自动分块并嵌入向量数据库（已实现，需验证）

### Requirement: 多类型图表支持
系统 SHALL 根据分析维度和数据特征，自动选择合适的图表类型生成可视化。

#### Scenario: 多维度对比分析
- **WHEN** 有 3+ 维度的洞察数据
- **THEN** 生成饼图（维度分布）和柱状图（维度-置信度对比）

#### Scenario: 时间序列数据
- **WHEN** 数据中包含 `published_date` 时间信息
- **THEN** 生成折线图展示时间趋势

## MODIFIED Requirements

### Requirement: AnalyzerOutput 新增 degraded 字段
`AnalyzerOutput` schema SHALL 新增 `degraded: bool = False` 字段，标记分析是否经过降级处理。

### Requirement: ReporterOutput 新增 degraded 字段
`ReporterOutput` schema SHALL 新增 `degraded: bool = False` 字段，标记报告是否经过降级处理。

### Requirement: ReporterOutput 新增 chart_images 字段
`ReporterOutput` schema SHALL 新增 `chart_images: List[Dict[str, str]] = []` 字段，存储渲染后的 base64 图表图片，格式为 `[{"title": "维度分布", "base64": "iVBOR..."}]`。

### Requirement: CollectorOutput 新增 warning 字段
`CollectorOutput` schema SHALL 新增 `warning: Optional[str] = None` 字段，用于区分"无结果"和"失败"。

### Requirement: OrchestratorOutput 新增 partial_results 字段
`OrchestratorOutput` schema SHALL 新增 `partial_results: Optional[Dict[str, Any]] = None` 字段，存储失败时的中间结果。

## REMOVED Requirements

无。所有已有功能保持不变。