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
