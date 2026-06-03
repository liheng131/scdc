# 修复工作流 LLM 调用超时问题 Spec

## Why
执行工作流时出现 `httpx.ReadTimeout` 错误，原因是：
1. AnalyzerAgent 和 ReporterAgent 的 LLM 调用超时设置为 60 秒
2. GPUStack 远程服务（120.79.96.231:6003）响应时间可能超过 60 秒
3. 重试次数设置为 1（`stop_after_attempt(1)`），超时后不重试
4. 超时后触发降级到规则分析，影响工作流输出质量

## What Changes
- 增加 AnalyzerAgent 和 ReporterAgent 的 LLM 调用超时时间
- 增加重试次数，允许在网络波动时自动重试
- 优化超时错误处理，提供更明确的错误信息

## Impact
- Affected code:
  - `backend/app/agents/analyzer.py` — `_call_llm` 方法的超时和重试配置
  - `backend/app/agents/reporter.py` — `_call_llm` 方法的超时和重试配置

## ADDED Requirements

### Requirement: LLM 调用超时与重试
系统 SHALL 为 LLM 调用设置合理的超时时间和重试机制：
- 默认超时：120 秒（适应远程模型服务）
- 重试次数：最多 2 次
- 重试间隔：指数退避（2-10 秒）

#### Scenario: 远程模型服务响应慢
- **WHEN** GPUStack 远程服务响应时间超过 60 秒
- **THEN** 等待最多 120 秒，若仍超时则自动重试 1 次

#### Scenario: 连续超时
- **WHEN** 重试 2 次后仍然超时
- **THEN** 抛出异常并记录详细错误信息，触发降级逻辑

## MODIFIED Requirements

### Requirement: AnalyzerAgent _call_llm 方法
系统 SHALL 修改 `analyzer.py` 中 `_call_llm` 方法：
- 默认 timeout 从 60 改为 120
- 重试次数从 1 改为 2

### Requirement: ReporterAgent _call_llm 方法
系统 SHALL 修改 `reporter.py` 中 `_call_llm` 方法：
- 默认 timeout 从 60 改为 120
- 重试次数从 1 改为 2
