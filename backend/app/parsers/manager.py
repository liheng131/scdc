"""
解析器管理器

根据文件扩展名自动路由到对应的解析器实例，提供统一的 parse_file() 入口。

为什么使用管理器模式：
- 隔离调用方与具体解析器实现，添加新格式只需注册新解析器
- 统一的错误处理（BusinessException），避免调用方逐一捕获
- .doc 和 .docx 共享 DocxParser，兼容旧格式 Word 文档
"""

from typing import BinaryIO
import pathlib
from app.parsers.base import BaseParser
from app.parsers.pdf import PDFParser
from app.parsers.docx import DocxParser
from app.parsers.excel import ExcelParser
from app.schemas.parser import ParseResult
from app.core.exceptions import BusinessException

class ParserManager:
    def __init__(self):
        self.parsers = {
            ".pdf": PDFParser(),
            ".docx": DocxParser(),
            ".doc": DocxParser(),
            ".xlsx": ExcelParser(),
            ".xls": ExcelParser(),
        }

    def get_parser(self, filename: str) -> BaseParser:
        """根据文件扩展名获取对应的解析器，不支持的类型抛出 BusinessException"""
        ext = pathlib.Path(filename).suffix.lower()
        parser = self.parsers.get(ext)
        if not parser:
            raise BusinessException(code=400, message=f"Unsupported file extension: {ext}")
        return parser

    async def parse_file(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        """统一入口：自动选择解析器并执行解析"""
        parser = self.get_parser(filename)
        return await parser.parse(file_stream, filename)
