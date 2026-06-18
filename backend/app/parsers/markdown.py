"""
Markdown 文档解析器

读取 UTF-8 编码的 Markdown 文本，按 H1/H2 标题切分章节；若文档不含标题则退化为按段落切分。

为什么按标题切分：
- Markdown 文档的章节语义由 # / ## 等标题定义，按标题切分能保留上下文结构
- 无标题时退化为段落切分，避免单块内容过大影响后续 LLM 处理
"""

import io
import re
from typing import BinaryIO

from app.parsers.base import BaseParser
from app.schemas.parser import ParseResult, Chunk
from app.core.exceptions import BusinessException


_HEADER_SPLIT_RE = re.compile(r"(?m)^#{1,2}\s+\S.*$")


class MarkdownParser(BaseParser):
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        try:
            text_wrapper = io.TextIOWrapper(file_stream, encoding="utf-8", errors="replace")
            content = text_wrapper.read()
            text_wrapper.detach()

            sections: list[str]

            matches = list(_HEADER_SPLIT_RE.finditer(content))
            if matches:
                strategy = "headers"
                # Leading content before the first header is its own section
                first_start = matches[0].start()
                if first_start > 0 and content[:first_start].strip():
                    sections = [content[:first_start]]
                else:
                    sections = []

                for idx, match in enumerate(matches):
                    section_start = match.start()
                    section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
                    sections.append(content[section_start:section_end])
            else:
                strategy = "paragraphs"
                sections = [p.strip() for p in content.split("\n\n") if p.strip()]

            chunks = [
                Chunk(
                    index=idx,
                    content=section.strip(),
                    metadata={"strategy": strategy},
                )
                for idx, section in enumerate(sections, start=1)
            ]

            return ParseResult(
                filename=filename,
                file_type="markdown",
                content=content,
                chunks=chunks,
                metadata={
                    "format": "markdown",
                    "char_count": len(content),
                    "chunk_strategy": strategy,
                },
            )
        except Exception as e:
            raise BusinessException(code=422, message=f"Failed to parse Markdown file: {str(e)}")
