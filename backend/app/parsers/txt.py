"""
纯文本解析器

读取 UTF-8 编码的纯文本文件，按段落（双换行）切分 Chunk。

为什么按段落切分：
- 纯文本没有结构化标签，双换行是最常见的段落分隔方式
- 单换行保留在同一 Chunk 中，避免破坏短行（如列表项）的语义
"""

import io
from typing import BinaryIO

from app.parsers.base import BaseParser
from app.schemas.parser import ParseResult, Chunk
from app.core.exceptions import BusinessException


class TxtParser(BaseParser):
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        try:
            text_wrapper = io.TextIOWrapper(file_stream, encoding="utf-8", errors="replace")
            content = text_wrapper.read()
            text_wrapper.detach()

            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            chunks = [
                Chunk(
                    index=idx,
                    content=para,
                    metadata={"strategy": "paragraphs"},
                )
                for idx, para in enumerate(paragraphs, start=1)
            ]

            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

            return ParseResult(
                filename=filename,
                file_type="txt",
                content=content,
                chunks=chunks,
                metadata={
                    "format": "text",
                    "char_count": len(content),
                    "line_count": line_count,
                },
            )
        except Exception as e:
            raise BusinessException(code=422, message=f"Failed to parse TXT file: {str(e)}")
