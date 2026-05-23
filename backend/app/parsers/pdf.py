"""
PDF 文档解析器

使用 pypdf 库逐页提取 PDF 文本内容，按页分块输出。

为什么按页分块（Chunk）而不是全文输出：
- PDF 文档可能长达数百页，全文直接传给 LLM 会超出上下文窗口
- 按页分块后 CollectorAgent 可以分批处理，逐页清洗和摘要
- metadata 记录页码，ReporterAgent 可以在报告中引用具体页码
"""

import io
from typing import BinaryIO
import pypdf
from app.parsers.base import BaseParser
from app.schemas.parser import ParseResult, Chunk
from app.core.exceptions import BusinessException

class PDFParser(BaseParser):
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        try:
            reader = pypdf.PdfReader(file_stream)
            full_text = []
            chunks = []

            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                full_text.append(text)
                if text.strip():
                    chunks.append(Chunk(
                        index=i + 1,
                        content=text.strip(),
                        metadata={"page": i + 1}
                    ))

            content = "\n\n".join(full_text)
            metadata = {
                "total_pages": len(reader.pages),
                "author": reader.metadata.author if reader.metadata else None,
                "title": reader.metadata.title if reader.metadata else None,
            }
            return ParseResult(
                filename=filename,
                file_type="pdf",
                content=content,
                chunks=chunks,
                metadata=metadata
            )
        except Exception as e:
            raise BusinessException(code=422, message=f"Failed to parse PDF file: {str(e)}")
