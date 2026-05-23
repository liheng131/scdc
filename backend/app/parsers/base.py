"""
文档解析器抽象基类

定义所有解析器的统一接口 parse()，接收文件二进制流并返回标准化的 ParseResult。

为什么接口参数是 BinaryIO 而不是文件路径：
- 文件可能来自 HTTP 上传（multipart/form-data），不经过磁盘
- 设计为内存流处理，避免临时文件管理的复杂性
"""

from abc import ABC, abstractmethod
from typing import BinaryIO
from app.schemas.parser import ParseResult

class BaseParser(ABC):
    @abstractmethod
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        """将文件二进制流解析为标准化的 ParseResult 结构"""
        pass
