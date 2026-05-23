"""
文档解析模块

支持多种格式文档的内容提取和分块：
- BaseParser: 解析器基类，定义核心接口
- PDFParser: PDF 文档解析（pypdf）
- DocxParser: Word 文档解析（python-docx）
- ExcelParser: Excel 表格解析（openpyxl）
- ParserManager: 解析器管理器，根据文件扩展名自动匹配解析器

为什么输出 ParseResult（包含 chunks 列表）而不是纯文本：
- LLM 的上下文窗口有限，整篇文档可能超过 token 限制
- chunks 按页/段落/Sheet 分块，便于 CleanerAgent 局部处理
- metadata 保留文档元信息，供 ReporterAgent 在报告中引用来源
"""
