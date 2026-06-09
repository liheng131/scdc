"""
报告向量库写入服务

封装"分块 → 嵌入 → 写 Milvus"流程，从 ReportService 解耦，
让 export / upload 端点都能按需触发。

为什么独立成 service：
- 报告生成（workflow）阶段不再污染 RAG 检索源（避免用户对生成结果不满意时
  重新生成却发现旧内容已入库）
- 真正"用户主动确认"的时机是首次导出（PDF/DOCX/PPTX/MD）或上传报告
"""
import logging
from typing import List

from app.models.report import Report
from app.services.embedding import EmbeddingService
from app.services.vectorstore import VectorStoreService

logger = logging.getLogger(__name__)


class VectorstoreUploadService:
    """统一的报告向量库写入服务"""

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
        if not text:
            return []
        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    async def upload_report(self, report: Report) -> int:
        """把报告嵌入到 Milvus

        Returns:
            写入的 chunk 数；0 表示未写入（无内容/嵌入失败/Milvus 未连接）
        """
        if not report or not report.content_markdown:
            return 0
        try:
            chunks = self._chunk_text(report.content_markdown)
            if not chunks:
                return 0
            emb_service = EmbeddingService()
            vectors = await emb_service.embed_texts_or_empty(chunks)
            if not vectors:
                logger.warning("Embedding returned empty for report %d", report.id)
                return 0
            vs_service = VectorStoreService()
            if not vs_service._connected:
                logger.warning("Milvus not connected, skipping upload for report %d", report.id)
                return 0
            vs_service.init_collection(len(vectors[0]))
            # 删除该 report_id 下的旧 chunk（防止重复入库或更新残留）
            try:
                vs_service.delete_by_report(str(report.id))
            except Exception as e:
                logger.warning("delete_by_report failed for report %d: %s", report.id, e)
            vs_service.insert(str(report.id), chunks, vectors)
            logger.info("Uploaded %d chunks for report %d to Milvus", len(chunks), report.id)
            return len(chunks)
        except Exception as e:
            logger.warning("Failed to upload report %d to Milvus: %s", report.id, e)
            return 0


vs_upload_service = VectorstoreUploadService()
