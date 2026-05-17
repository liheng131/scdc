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
        ext = pathlib.Path(filename).suffix.lower()
        parser = self.parsers.get(ext)
        if not parser:
            raise BusinessException(code=400, message=f"Unsupported file extension: {ext}")
        return parser

    async def parse_file(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        parser = self.get_parser(filename)
        return await parser.parse(file_stream, filename)
