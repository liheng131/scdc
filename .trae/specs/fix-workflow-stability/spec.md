# 工作流稳定性修复 Spec

## Why
之前两个 spec 的代码修改因 Docker 未重建而从未生效。此外 LLM 调用超时 300s+2次重试导致 analyzing/reporting 阶段各需约 10 分钟才能降级到规则分析，前端在此期间无任何反馈看似卡死。导出失败因 `reports.task_id` 列仍是 INTEGER，字符串 workflow_id 写入被数据库拒绝。

## What Changes
- 将 AnalyzerAgent 和 ReporterAgent 的 LLM 调用超时从 300s 降至 60s，降级重试次数从 2 次降至 1 次（连接异常直接降级到规则分析）
- 在 `_call_llm` 中增加 `httpx.ConnectError` 和 `httpx.ConnectTimeout` 到重试异常列表，确保网络连接失败时立即走降级路径
- 更新 `docker-compose.yml` 和 `Dockerfile` 确保 `python-pptx` 依赖在容器内正确安装
- 前端 SSE 连接增加超时和重连逻辑，连接断开后自动重试
- 前端在长期无进度时（1 分钟）自动显示"部分阶段可能耗时较久"的提示

## Impact
- Affected specs: fix-workflow-conversation-llm-export, fix-export-and-report-sync
- Affected code:
  - `backend/app/agents/analyzer.py` - LLM 超时 300s→60s，重试 2→1
  - `backend/app/agents/reporter.py` - 同上
  - `backend/Dockerfile` - 确保 python-pptx 安装
  - `frontend/src/stores/workflow.ts` - SSE 重连逻辑
  - `frontend/src/views/WorkflowView.vue` - 长时间无进度提示

## MODIFIED Requirements

### Requirement: LLM 调用超时策略
LLM 调用 SHALL 使用 60s 超时而非 300s，网络连接失败时立即降级而不等待超时。

#### Scenario: LLM 服务可连接但响应慢
- **WHEN** LLM 调用超时 60s
- **THEN** 记录 WARNING 日志并降级到规则分析

#### Scenario: LLM 服务不可达
- **WHEN** 连接被拒绝或 DNS 解析失败
- **THEN** 立即记录 WARNING 并降级，不等待超时

### Requirement: SSE 连接稳定性
前端 SSE 连接 SHALL 支持断开后自动重连，并在长期无进度时提示用户。

#### Scenario: 工作流某个阶段耗时超过 60s
- **WHEN** 前端超过 60s 未收到 SSE 事件
- **THEN** 显示提示"当前阶段可能耗时较久，请耐心等待..."

#### Scenario: SSE 连接意外断开
- **WHEN** EventSource 因网络波动断开
- **THEN** 自动重连一次（使用同一 workflow_id 和 token）

### Requirement: Docker 构建完整性
Docker 构建 SHALL 确保所有 Python 依赖正确安装。

#### Scenario: 导出 PPTX 格式
- **WHEN** 用户选择导出为 pptx
- **THEN** `python-pptx` 库可用并成功生成 PPTX 文件