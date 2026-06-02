# Checklist

- [x] IntentClassifier 能正确识别市场洞察类请求（如"2025年AI芯片市场趋势"），返回 `market_insight`
- [x] IntentClassifier 能正确识别一般问答类请求（如"你能做什么""今天天气怎么样""计算球体面积"），返回 `general_question`
- [x] IntentClassifier 能正确识别工作流回退请求（如"报告不够详细请重新分析""数据不准请重新采集"），返回 `workflow_reentry` 并附带正确的 `target_stage`
- [x] 一般问答请求走直接应答路径，不触发数据采集、清洗、分析、报告流程
- [x] 直接应答路径通过 SSE 流式返回 LLM 回答，前端正常显示内容且不展示四阶段进度条
- [x] 市场洞察请求正常走四阶段流水线，前端正常展示进度条和最终报告
- [x] 回退到 reporting 阶段时，复用已有的 AnalyzerOutput，重新生成报告，用户补充约束被注入 prompt
- [x] 回退到 analyzing 阶段时，复用已有的 CleanedItems，重新分析，完成后自动执行 reporting 阶段
- [x] 回退到 collecting 阶段时，携带用户补充约束重新搜索，走完整四阶段流程
- [x] 回退过程中某一阶段失败时，前端正确展示错误信息和部分结果
- [x] 前端报告完成后显示回退按钮（"重新分析""重新采集"等）
- [x] 前端点击回退按钮后可输入补充约束并触发回退流程
- [x] OrchestratorInput 支持 `start_stage` 参数，从非 collecting 阶段切入时正确跳过前置阶段
- [x] 回退流 SSE 事件能正确渲染前端进度条和最终结果
- [x] 现有正向流程（从 collecting 开始的完整流水线）不受影响，行为与改造前一致