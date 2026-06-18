"""
图片 OCR 解析器

使用 Pillow 打开图片，再调用 pytesseract 提取图片中的文字内容。
优先使用中英文双语模型（chi_sim+eng），若 Tesseract 未安装中文语言包或调用失败，
自动回退到英文模型（eng），保证基本可用性。

为什么需要图片 OCR：
- 用户上传的报告常包含截图、扫描件等图片形式
- 将图片中的文字提取为文本后，可以和普通文档一样进入 CollectorAgent
"""

import io
import logging
import pathlib
from typing import BinaryIO

from app.parsers.base import BaseParser
from app.schemas.parser import ParseResult, Chunk
from app.core.exceptions import BusinessException

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a required dependency
    Image = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - pytesseract is optional at import time
    pytesseract = None


class ImageOcrParser(BaseParser):
    async def parse(self, file_stream: BinaryIO, filename: str) -> ParseResult:
        try:
            if Image is None:
                raise BusinessException(
                    code=422,
                    message="Failed to OCR image: Pillow is not installed",
                )

            img = Image.open(file_stream)
            width, height = img.size
            fmt = (img.format or "").lower() or pathlib.Path(filename).suffix.lstrip(".").lower()

            # 如果 pytesseract 未安装,或 Tesseract 引擎缺失(常见于 Windows dev 环境),
            # 不抛错,而是返回"OCR 不可用"占位结果,避免阻塞用户的图片上传
            if pytesseract is None:
                return self._unavailable_result(
                    filename, fmt, width, height,
                    reason="pytesseract Python 包未安装",
                )

            try:
                text, ocr_lang = self._run_ocr(img)
            except Exception as ocr_exc:
                # Tesseract 引擎不存在 / 语言包缺失 / 图像解码失败 等
                logger.warning(
                    "OCR engine unavailable for %s, returning placeholder: %s",
                    filename, ocr_exc,
                )
                return self._unavailable_result(
                    filename, fmt, width, height,
                    reason=f"OCR 引擎不可用: {ocr_exc}",
                )

            content = f"[图片 OCR 识别结果 - {width}x{height}]\n\n{text}"

            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [text.strip()] if text.strip() else [""]

            chunks = [
                Chunk(
                    index=idx,
                    content=para,
                    metadata={"strategy": "ocr"},
                )
                for idx, para in enumerate(paragraphs, start=1)
            ]

            return ParseResult(
                filename=filename,
                file_type="image",
                content=content,
                chunks=chunks,
                metadata={
                    "format": fmt,
                    "image_dimensions": {"width": width, "height": height},
                    "ocr_engine": "tesseract",
                    "ocr_lang": ocr_lang,
                },
            )
        except BusinessException:
            raise
        except Exception as e:
            raise BusinessException(code=422, message=f"Failed to OCR image: {str(e)}")

    @staticmethod
    def _unavailable_result(
        filename: str, fmt: str, width: int, height: int, reason: str
    ) -> ParseResult:
        """OCR 不可用时的占位结果(图片元数据保留)"""
        content = (
            f"[图片 - {width}x{height} {fmt}]\n\n"
            f"⚠️ OCR 不可用: {reason}\n"
            f"请在系统中安装 Tesseract OCR 引擎后重试:\n"
            f"  - Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            f"  - Linux: apt install tesseract-ocr tesseract-ocr-chi-sim\n"
        )
        return ParseResult(
            filename=filename,
            file_type="image",
            content=content,
            chunks=[Chunk(index=1, content=content, metadata={"strategy": "ocr_unavailable"})],
            metadata={
                "format": fmt,
                "image_dimensions": {"width": width, "height": height},
                "ocr_engine": "unavailable",
                "ocr_lang": "n/a",
                "warning": reason,
            },
        )

    @staticmethod
    def _run_ocr(img) -> tuple[str, str]:
        """尝试使用中英文模型进行 OCR，失败时回退到英文模型。返回 (text, used_lang)。"""
        try:
            return pytesseract.image_to_string(img, lang="chi_sim+eng"), "chi_sim+eng"
        except Exception as exc:
            logger.warning(
                "pytesseract failed with lang='chi_sim+eng', falling back to lang='eng': %s",
                exc,
            )
            return pytesseract.image_to_string(img, lang="eng"), "eng"
