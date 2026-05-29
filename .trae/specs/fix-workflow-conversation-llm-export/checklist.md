# Checklist

- [x] Report 模型 task_id 字段类型为 Optional[str]，无 ForeignKey 约束
- [x] ReportCreate 和 ReportOut schema 中 task_id 类型为 Optional[str]
- [x] 工作流完成后报告成功写入数据库（_save_report 不再静默失败）
- [x] 工作流页面导出非 md 格式文件时，能正确按 workflow_id 查找报告并下载
- [x] 智能报告页面正常展示导出报告列表，task_id 为字符串格式
- [x] 智能体工作流页面顶部显示"新建对话"按钮
- [x] 点击"新建对话"可清空当前会话回到空状态
- [x] 工作流执行中点击"新建对话"时弹出确认对话框
- [x] runtime_config._DEFAULTS 包含 llm_base_url
- [x] AnalyzerAgent 和 ReporterAgent 从 runtime_config 读取 llm_base_url
- [x] 系统设置页可编辑 LLM 服务地址并保存生效
- [x] 系统设置页"测试连接"按钮能检测 LLM 服务连通性
- [x] GET /api/v1/settings/llm-health 端点返回正确的健康状态