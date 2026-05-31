# 修复报告生成乱码与图表显示问题 Spec

## Why
当前工作流生成的报告存在两个严重问题：
1. PDF 文件解析失败，原始 PDF 二进制内容（如 `%PDF-1.3 % 1 0 obj`）直接进入报告，产生大量乱码
2. matplotlib 生成的图表中所有中文标题和坐标轴标签显示为方块（□□□□），因为后端容器缺少中文字体

## What Changes
- 改进 PDFParser：增加文本提取后的内容清洗，丢弃纯二进制/无意义内容
- 改进 CleanerAgent：增加内容格式检测，过滤掉 PDF 原始二进制内容
- 修复 ReporterAgent 图表：配置 matplotlib 使用支持中文的字体

## Impact
- 受影响的模块：PDF 解析、数据清洗、报告生成
- 受影响的文件：
  - `backend/app/parsers/pdf.py`
  - `backend/app/agents/cleaner.py`
  - `backend/app/agents/reporter.py`
  - `backend/Dockerfile`（可能需要添加中文字体包）

## ADDED Requirements
### Requirement: 内容格式清洗
系统 SHALL 在数据清洗阶段检测并过滤掉非人类可读的内容（如 PDF 原始二进制、图片二进制数据等）。

#### Scenario: PDF 二进制内容被过滤
- **WHEN** PDF 解析器提取的内容包含 `%PDF` 头部标记或大量不可打印字符
- **THEN** 该条目应在清洗阶段被标记为无效并丢弃，或记录 warning 日志

### Requirement: 图表中文正常显示
系统 SHALL 在生成报告图表时正确渲染所有中文字符，不出现方块占位符。

#### Scenario: 饼图和柱状图标题使用中文
- **WHEN** ReporterAgent 生成包含中文维度的饼图和柱状图
- **THEN** 所有标题、图例、坐标轴标签均以清晰的中文显示

## MODIFIED Requirements
### Requirement: PDF 文本提取
PDF 解析器 SHALL 验证提取的文本是否为有效的人类可读内容。如果页面提取的内容主要是控制字符或二进制数据，则应跳过该页面。

#### Scenario: 扫描件/图片PDF处理
- **WHEN** PDF 页面是扫描件或包含嵌入图片（无OCR文本层）
- **THEN** `extract_text()` 返回的内容应被检测并跳过，不进入后续处理流程

## REMOVED Requirements
无
