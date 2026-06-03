# Fix Workflow LLM Timeout Checklist

- [ ] analyzer.py 中 _call_llm 默认 timeout 改为 120 秒
- [ ] analyzer.py 中重试次数改为 2 次
- [ ] reporter.py 中 _call_llm 默认 timeout 改为 120 秒
- [ ] reporter.py 中重试次数改为 2 次
- [ ] 工作流执行时 LLM 调用不再超时（或超时后自动重试成功）
