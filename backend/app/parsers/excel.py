import io
from typing import BinaryIO
import openpyxl
from app.parsers.base import BaseParser
from app.schemas.parser import ParseResult, Chunk
from app.core.exceptions import BusinessException

class ExcelParser(BaseParser):
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        try:
            wb = openpyxl.load_workbook(file_stream, data_only=True)
            full_text = []
            chunks = []
            chunk_idx = 1
            
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                sheet_text = [f"--- Sheet: {sheet_name} ---"]
                
                for row_idx, row in enumerate(sheet.iter_rows(values_only=True)):
                    row_vals = [str(cell) for cell in row if cell is not None]
                    if row_vals:
                        row_str = " | ".join(row_vals)
                        sheet_text.append(row_str)
                        
                if len(sheet_text) > 1:
                    content = "\n".join(sheet_text)
                    full_text.append(content)
                    chunks.append(Chunk(
                        index=chunk_idx,
                        content=content,
                        metadata={"sheet": sheet_name, "rows": len(sheet_text) - 1}
                    ))
                    chunk_idx += 1
            
            content = "\n\n".join(full_text)
            return ParseResult(
                filename=filename,
                file_type="xlsx",
                content=content,
                chunks=chunks,
                metadata={"sheet_names": wb.sheetnames}
            )
        except Exception as e:
            raise BusinessException(code=422, message=f"Failed to parse Excel file: {str(e)}")
