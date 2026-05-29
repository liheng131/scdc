# 报告多格式导出、智能报告页面与AI模型设置实时生效 Spec

## Why
当前系统仅支持 Markdown 格式的报告导出，且缺少集中的报告管理页面；同时系统设置中的 AI 大模型配置并未与实际推理引擎联动，修改配置后不生效。需要补齐这三块能力。

## What Changes
- 报告导出新增 PPT 格式支持（已有 DOCX/PDF/MD），前端提供四种格式的选择下载
- 左侧导航新增"智能报告"页面，展示所有已生成报告，支持删除、修改标题、预览、模糊搜索等常规管理功能
- 后端新增运行时系统配置 API，前端设置页面保存后实时更新 AI 推理引擎参数（Provider/API Key/Model/Temperature/MaxTokens）
- 工作流完成后自动将报告存入数据库

## Impact
- Affected specs: reports，workflow，settings
- Affected code: 后端 report 服务/模型/路由、workflow 服务、config 模块、新增 settings API 路由；前端 WorkflowView、MainLayout、router、新增 SmartReportsView、改造 SettingsView、新增 settings/reports API 服务

## ADDED Requirements

### Requirement: 报告多格式导出
系统 SHALL 支持将报告导出为 Markdown、DOCX（Word）、PDF、PPTX（PowerPoint）四种格式，用户在导出时可选择格式。

#### Scenario: 用户导出报告为 PPT
- **WHEN** 用户在工作流对话结果区域点击导出按钮，选择 PPT 格式
- **THEN** 浏览器下载生成 .pptx 文件

#### Scenario: 用户从智能报告页面导出
- **WHEN** 用户在智能报告页面选择一份报告，点击导出并选择格式
- **THEN** 浏览器下载对应格式文件

### Requirement: 智能报告管理页面
系统 SHALL 在左侧导航栏提供"智能报告"入口，打开后展示所有已生成的报告列表，支持搜索、预览、修改标题、删除操作。

#### Scenario: 查看报告列表
- **WHEN** 用户点击左侧"智能报告"菜单
- **THEN** 页面展示所有报告卡片/列表，每条包含标题、生成时间、状态

#### Scenario: 搜索报告
- **WHEN** 用户在搜索框输入关键词
- **THEN** 列表实时过滤匹配标题或摘要的报告

#### Scenario: 预览报告
- **WHEN** 用户点击某条报告的"预览"按钮
- **THEN** 弹出对话框展示该报告的 Markdown 渲染内容及图表

#### Scenario: 修改报告标题
- **WHEN** 用户在列表中对某条报告点击编辑标题
- **THEN** 标题变为可编辑状态，确认后更新数据库

#### Scenario: 删除报告
- **WHEN** 用户点击删除按钮并确认
- **THEN** 报告从数据库移除，列表刷新

### Requirement: AI 模型设置实时生效
系统 SHALL 提供后端配置读写 API，前端设置页面保存后实时更新推理引擎参数，后续工作流执行时使用最新配置。

#### Scenario: 修改 LLM Provider 并生效
- **WHEN** 用户在设置页修改模型供应商从 ollama 切换为 gpustack，填写新的 API Key 和 Model 名称，点击保存
- **THEN** 后端运行时配置立即更新，下次发起工作流分析时使用新配置

#### Scenario: 修改 Temperature 并生效
- **WHEN** 用户将 temperature 从 0.3 调整为 0.7 并保存
- **THEN** 后续 LLM 调用使用新的 temperature 参数

## MODIFIED Requirements

### Requirement: 工作流完成自动保存报告
工作流执行完成（SSE completed 事件）时，系统 SHALL 自动将最终报告存储到数据库 reports 表中。

#### Scenario: 分析完成后报告自动入库
- **WHEN** 工作流 SSE 流发送 completed 事件后
- **THEN** 报告以 title=topic、status=published 写入 reports 表，智能报告页面可立即看到