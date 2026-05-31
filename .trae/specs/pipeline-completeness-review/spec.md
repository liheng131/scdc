# 全流程验收与完整性增强 Spec

## Why

用户需要确认整个分析流水线（SerpAPI 搜索 → 爬虫抓取 → 数据清洗 → 向量检索 → LLM 分析 → 报告生成 → 多格式导出）功能正常、无报错、无不可控的降级，并找出缺失环节逐个修复。

## What Changes

- **修复** `OrchestratorAgent.execute()` 参数传递 — 当前 `AnalyzerInput` 和 `ReporterInput` 未接收 `dimensions`/`source_contents` 字段
- **修复** `workflow.py` 与 `OrchestratorAgent` 代码重复 — 两套四阶段调用逻辑完全独立，应统一复用
- **新增** 工作流持久化 — `WorkflowService` 当前仅内存存储，重启后历史丢失
- **新增** 自动报告入库 — 工作流完成后应自动将报告写入 `reports` 表
- **新增** 端到端集成测试脚本 — 一键验证全流程
- **优化** 前端阶段统计展示 — 展示采集数量、清洗前后对比、洞察数量

## Impact

- Affected specs: `fix-workflow-stability`, `reports-vector-upload`
- Affected code: `backend/app/services/workflow.py`, `backend/app/agents/orchestrator.py`, `backend/app/schemas/agent.py`, `frontend/src/views/WorkflowView.vue`

## ADDED Requirements

### Requirement: 工作流持久化
系统 SHALL 将工作流状态持久化到 PostgreSQL 数据库，支持跨重启恢复。

#### Scenario: 服务重启后恢复工作流
- **WHEN** 后端服务重启
- **THEN** 已完成的工作流历史不丢失，可在"历史记录"中查看

### Requirement: 自动报告入库
系统 SHALL 在工作流完成后自动将生成的报告写入 `reports` 表。

#### Scenario: 工作流完成自动入库
- **WHEN** 工作流状态变为 `completed`
- **THEN** 报告内容（markdown、summary、task_id）自动写入数据库，可在"智能研报"页面查询和导出

### Requirement: 端到端集成测试
系统 SHALL 提供一键端到端测试脚本，验证全流程无报错。

#### Scenario: 运行集成测试
- **WHEN** 用户执行测试脚本
- **THEN** 脚本执行 SerpAPI 搜索 → 爬虫 → 清洗 → 分析 → 报告生成，全部成功返回

### Requirement: 阶段统计展示
系统 SHALL 在前端展示每个阶段的统计信息（采集数量、清洗前后对比、洞察数量）。

#### Scenario: 用户查看阶段统计
- **WHEN** 工作流执行过程中某阶段完成
- **THEN** 前端消息气泡中显示该阶段的统计数据

## MODIFIED Requirements

### Requirement: OrchestratorAgent 参数传递
`OrchestratorAgent.execute()` 中 `AnalyzerInput` 创建时 SHALL 传入 `input_data.dimensions`；`ReporterInput` 创建时 SHALL 传入 `input_data.dimensions` 和 `source_contents`。

### Requirement: 工作流引擎统一编排
`workflow.py` SHALL 复用 `OrchestratorAgent.execute()`，而非手动逐个调用 Agent。通过 `state_callback` 桥接到 SSE 流推送。

## REMOVED Requirements

无。所有已有功能保持不变，均为增强和修复。