# Checklist

- [x] 意图分类器已集成到 `WorkflowService`，`_classify_intent()` 方法可用
- [x] 直接应答服务已集成到 `WorkflowService`，`run_direct_response_stream()` 方法可用
- [x] 回退流 `run_reentry_stream()` 方法已实现，支持从 collecting / analyzing / reporting 切入
- [x] `run_workflow_stream()` 支持 `start_stage` 和 `reentry_context` 参数
- [x] `POST /start` 端点先进行意图分类，根据结果分流到不同路径
- [x] `general_question` 意图返回 `StreamingResponse` 直接应答，不创建 WorkflowRun
- [x] `market_insight` 意图走原有正常流水线
- [x] `POST /{workflow_id}/reentry` 端点已添加，支持回退执行
- [x] `OrchestratorAgent.execute()` 支持 `start_stage` 从 collecting / analyzing / reporting 切入
- [x] 回退到 `analyzing` 阶段时跳过采集+清洗，复用 `previous_output` 中的 CleanedItems
- [x] 回退到 `reporting` 阶段时跳过采集+清洗+分析，复用 `previous_output` 中的 AnalyzerOutput
- [x] `state.result` 中存储 `chart_images`（渲染后的 base64 图片列表）
- [x] 报告自动保存时传递 `chart_images`（`[{title: str, base64: str}]`）而非 `chart_configs`（ECharts 配置对象）
- [x] `ReportCreate` 校验通过，不再出现 `chart_images` 类型校验错误
- [x] `_embed_ollama()` 在 DNS 解析失败时优雅降级，返回空列表而非抛出异常