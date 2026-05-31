# 修复报告导出图片乱码与消失问题 Spec

## Why
工作流生成的报告包含 chart_images（base64 编码的 PNG 图表），但在 `create_from_workflow` 保存报告到数据库时，chart_images 没有被存入 `reports.images` 字段。导出 DOCX/PDF/PPTX 时，`r.images` 为空，导致图表消失。

另外，ReportImageItem schema 和 ReporterAgent 生成的 chart_images 格式不匹配：
- ReporterAgent 生成格式：`{"title": str, "base64": str}`
- ReportImageItem 格式：`{"section": str, "prompt": str, "image_url": str, "position": int}`

这导致即使有数据，导出逻辑也无法正确读取图片。

## What Changes
- 修改 workflow 保存逻辑：将 reporter_output.chart_images 存入数据库 reports 表
- 统一 chart_images 存储格式：使用 `{"title": str, "base64": str}` 格式
- 确保 DOCX/PDF/PPTX 导出时能正确读取并渲染图片
- 修改 PDF 导出中的临时文件处理为更安全的方式

## Impact
- Affected specs: fix-export-and-report-sync
- Affected code:
  - `backend/app/services/workflow.py` - 保存 report 时持久化 chart_images
  - `backend/app/services/report.py` - 导出逻辑读取 chart_images
  - `backend/app/schemas/report.py` - ReportImageItem schema

## ADDED Requirements
### Requirement: 报告保存时持久化图表
系统 SHALL 在通过工作流创建报告时，将 ReporterAgent 生成的 chart_images 数据存入数据库 reports 表的 images 字段。

#### Scenario: 工作流完成时保存图表
- **WHEN** 工作流完成并调用 `create_from_workflow`
- **THEN** chart_images 数据应被序列化并存入 reports.images 字段
- **AND** 导出时能正确读取并渲染图表

## MODIFIED Requirements
### Requirement: 图表图片存储格式
系统 SHALL 统一 chart_images 的存储格式为 `{"title": str, "base64": str}`，与 ReporterAgent 生成的格式保持一致。

### Requirement: DOCX/PDF/PPTX 导出图片处理
`generate_docx()`、`generate_pdf()`、`generate_pptx()` 方法 SHALL 正确读取数据库中的 chart_images 并渲染到导出文件中。

#### Scenario: PDF 导出包含图表
- **WHEN** 用户导出 PDF 格式报告且报告包含 chart_images
- **THEN** 图表应正确渲染在 PDF 中，不出现乱码或消失
- **AND** PDF 中文内容使用正确的中文字体显示

#### Scenario: DOCX 导出包含图表
- **WHEN** 用户导出 DOCX 格式报告且报告包含 chart_images
- **THEN** 图表应正确嵌入 DOCX 文件中，不出现乱码或消失

#### Scenario: PPTX 导出包含图表
- **WHEN** 用户导出 PPTX 格式报告且报告包含 chart_images
- **THEN** 图表应正确嵌入 PPTX 文件中，不出现乱码或消失

## REMOVED Requirements
无
