# 智能报告 × 向量数据库集成

## Why
1. 非 Markdown 格式导出依然失败，需要排查前端的实际运行时行为
2. 当前工作流完成后自动保存报告到数据库，但用户期望仅手动导出时才保存
3. 报告缺乏向量检索能力，无法将历史报告作为分析上下文
4. 智能报告页缺少手动上传报告的功能入口

## What Changes

### 一、导出自存入逻辑变更
- **移除** 工作流完成后自动调用 `_save_report` 的行为
- **新增** 用户在任意页面点击"导出报告"时，先保存到数据库再下载文件
- 导出接口 `/api/v1/reports/{id}/export` 改为 **非幂等**：导出即创建报告记录（如果首次导出）

### 二、向量数据库集成（Milvus + Embedding）
- **新增** `backend/app/services/vectorstore.py`：封装 Milvus 集合管理与向量操作
- **新增** `backend/app/services/embedding.py`：通过 Ollama/GPUStack embedding 接口生成文本向量
- 报告保存到数据库后，异步将报告内容分块嵌入并存入 Milvus
- 删除报告时，同步删除对应 Milvus 中的向量

### 三、智能报告页手动上传
- **新增** 前端上传对话框：支持 `.md`、`.pdf`、`.docx`、`.pptx`、`.txt` 文件
- **新增** `POST /api/v1/reports/upload` 接口：解析文件 → 存入数据库 → 嵌入向量库
- `.pdf` 和 `.docx` 使用现有 parser 模块解析文本内容

### 四、分析流程上下文增强
- **修改** `AnalyzerAgent.execute()`：在分析前从 Milvus 检索与 topic 语义相关的历史报告片段
- 将检索结果注入分析 LLM prompt 的"上下文背景"部分
- 当向量库为空时静默跳过（不影响正常流程）

## Impact
- Affected specs: fix-export-and-report-sync（auto-save 行为变更）、fix-export-auth（导出接口语义变更）
- Affected code:
  - `backend/app/services/workflow.py`（移除 auto-save）
  - `backend/app/services/report.py`（新增 upload、embed 方法）
  - `backend/app/api/routes/reports.py`（新增 upload 端点、修改 export 逻辑）
  - `backend/app/agents/analyzer.py`（注入向量上下文）
  - `frontend/src/views/ReportsView.vue`（新增上传 UI）
  - `frontend/src/views/WorkflowView.vue`（export 后触发保存）

## ADDED Requirements

### Requirement: 导出即保存
用户点击导出按钮时，系统 SHALL 先将报告保存到数据库（如果尚未保存），再返回文件下载流。同一个报告多次导出不会重复创建数据库记录。

#### Scenario: 工作流完成后首次导出
- **WHEN** 用户在工作流页面点击导出 PDF
- **THEN** 系统检查该 workflow_id 是否已有报告记录，若无则创建，然后返回 PDF 文件流

#### Scenario: 重复导出同一报告
- **WHEN** 用户对已导出的工作报告再次导出 DOCX
- **THEN** 系统直接返回 DOCX 文件流，不重复创建数据库记录

### Requirement: 报告向量化
报告保存到数据库后，系统 SHALL 将报告标题+摘要+内容分块（chunk size=512, overlap=64），通过 embedding 模型生成向量，存入 Milvus 集合 `scdc_reports`。

#### Scenario: 报告保存后自动嵌入
- **WHEN** 报告成功保存到 PostgreSQL
- **THEN** 系统在后台异步将报告内容分块并嵌入到 Milvus，日志记录嵌入成功条数

#### Scenario: 删除报告时同步清除向量
- **WHEN** 用户删除一个报告
- **THEN** 系统同步删除 Milvus 中该报告对应的所有向量分块

### Requirement: 手动上传报告
智能报告页 SHALL 提供"上传报告"按钮，用户可选择 `.md`、`.pdf`、`.docx`、`.pptx`、`.txt` 文件上传。系统解析文本内容后存入报告表和向量库。

#### Scenario: 上传 PDF 报告
- **WHEN** 用户上传一个 PDF 文件
- **THEN** 系统使用现有 PDF parser 提取文本，创建报告记录，嵌入到 Milvus

### Requirement: 分析上下文检索
AnalyzerAgent 在执行分析前 SHALL 从 Milvus 检索与 topic 语义相似的历史报告片段（top_k=3），将片段内容注入分析 prompt 的"历史上下文"部分。

#### Scenario: 向量库有相关内容
- **WHEN** AnalyzerAgent 分析 "2025年AI芯片市场趋势"，且向量库中有标题包含"AI芯片"的历史报告
- **THEN** 检索到的相关片段被注入 LLM prompt，辅助生成更全面的分析

#### Scenario: 向量库为空
- **WHEN** AnalyzerAgent 执行分析但 Milvus 中无任何报告
- **THEN** 跳过上下文检索，静默降级到原有分析流程