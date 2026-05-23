"""
AI Agent 流水线模块

包含五个 Agent，形成完整的数据处理流水线：
  CollectorAgent  → 数据采集（SearXNG 搜索 + HTTP 爬虫）
  CleanerAgent    → 数据清洗（去重、过滤、文本分块）
  AnalyzerAgent   → AI 分析（调用 Ollama LLM 提取洞察）
  ReporterAgent   → 报告生成（结构化 Markdown 报告 + 图表）
  OrchestratorAgent → 全流程编排（串联上述四阶段）

每个 Agent 独立可测试、可替换，符合单一职责原则。
"""
