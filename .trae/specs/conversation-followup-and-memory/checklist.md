# 对话追问与记忆功能 - 验证清单

- [x] ReporterInput 能正常接收 conversation_history 参数
- [x] FollowUpRequest 能正常通过 Pydantic 验证
- [x] POST /api/v1/workflow/follow-up 接口返回 SSE 格式流式数据
- [x] LLM 能收到包含 conversation_history 的 prompt
- [x] 带有 conversation_history 的 ReporterInput 能正确生成包含历史引用的 prompt
- [x] _run_follow_up 能正确接收消息和历史并调用 LLM
- [x] appendFollowUpMessage 正确将消息追加到当前对话
- [x] 追问消息正确保存到 localStorage
- [x] 首次发送显示"开始分析"，已有对话完成后显示"发送追问"
- [x] 工作流执行中时输入框不可用
- [x] 追问消息正确显示在当前对话中
- [x] 后端容器已重新构建并重启
- [x] 前端容器已重新构建并重启
- [ ] 完整流程测试通过：首次分析→查看结果→追问→查看追问结果
- [ ] 对话历史侧边栏正确显示所有对话
- [ ] 切换对话后能正确恢复上下文