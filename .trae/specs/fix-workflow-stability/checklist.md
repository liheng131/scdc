# Checklist

- [x] AnalyzerAgent._call_llm timeout 参数为 60（非 300）
- [x] AnalyzerAgent._call_llm retry stop_after_attempt 为 1（非 2）
- [x] AnalyzerAgent._call_llm retry 包含 ConnectError 和 ConnectTimeout
- [x] ReporterAgent._call_llm timeout 参数为 60（非 300）
- [x] ReporterAgent._call_llm retry stop_after_attempt 为 1（非 2）
- [x] ReporterAgent._call_llm retry 包含 ConnectError 和 ConnectTimeout
- [x] backend/requirements.txt 包含 python-pptx
- [x] Docker 构建成功后 python-pptx 在容器内可用
- [x] Task 1-3 全部完成后重新构建并部署 Docker
- [x] 后端启动日志中出现 "Successfully migrated reports.task_id to varchar(50)"
- [x] 工作流全程 SSE 进度事件正常（stage_start → stage_complete × 4 → completed）
- [x] LLM 不可用时 analyzing 阶段自动降级到规则分析
- [x] 工作流完成后非 md 格式文件可成功导出（docx/pdf/pptx）
- [x] 智能报告页面能展示所有工作流报告