"""
PDF 文档解析器

使用 pypdf 库逐页提取 PDF 文本内容，按页分块输出。

为什么按页分块（Chunk）而不是全文输出：
- PDF 文档可能长达数百页，全文直接传给 LLM 会超出上下文窗口
- 按页分块后 CollectorAgent 可以分批处理，逐页清洗和摘要
- metadata 记录页码，ReporterAgent 可以在报告中引用具体页码
"""

import io
import logging
from typing import BinaryIO

import pypdf

from app.parsers.base import BaseParser
from app.schemas.parser import ParseResult, Chunk
from app.core.exceptions import BusinessException

logger = logging.getLogger(__name__)

INVALID_CHAR_RATIO_THRESHOLD = 0.6

def _is_valid_text(text: str) -> bool:
    if not text:
        return False

    if text.startswith("%PDF"):
        return False

    total = len(text)
    control_count = sum(1 for ch in text if ch < " " and ch not in ("\n", "\r", "\t"))

    return (control_count / total) <= INVALID_CHAR_RATIO_THRESHOLD

class PDFParser(BaseParser):
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        try:
            reader = pypdf.PdfReader(file_stream)
            full_text = []
            chunks = []
            valid_pages = 0
            invalid_pages = 0

            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""

                if not _is_valid_text(text):
                    logger.warning(f"Skipping page {i + 1} due to invalid/garbled content in {filename}")
                    invalid_pages += 1
                    continue

                full_text.append(text)
                valid_pages += 1
                if text.strip():
                    chunks.append(Chunk(
                        index=i + 1,
                        content=text.strip(),
                        metadata={"page": i + 1}
                    ))

            content = "\n\n".join(full_text)
            metadata = {
                "total_pages": len(reader.pages),
                "valid_pages": valid_pages,
                "invalid_pages": invalid_pages,
                "author": reader.metadata.author if reader.metadata else None,
                "title": reader.metadata.title if reader.metadata else None,
            }

            if valid_pages == 0 and invalid_pages > 0:
                logger.warning(f"All pages in {filename} contain invalid/garbled content")
                metadata["warning"] = "All pages contain invalid or garbled content"

            return ParseResult(
                filename=filename,
                file_type="pdf",
                content=content,
                chunks=chunks,
                metadata=metadata
            )
        except Exception as e:
            raise BusinessException(code=422, message=f"Failed to parse PDF file: {str(e)}")
