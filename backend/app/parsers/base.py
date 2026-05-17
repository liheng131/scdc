from abc import ABC, abstractmethod
from typing import BinaryIO
from app.schemas.parser import ParseResult

class BaseParser(ABC):
    @abstractmethod
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        """Parse file binary stream into ParseResult"""
        pass
