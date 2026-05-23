"""
CleanerAgent（数据清洗 Agent）

职责：
- 接收 CollectorAgent 采集的原始数据，执行三道清洗工序
- ① 质量过滤：丢弃内容过短的低质量条目
- ② URI 去重：同一 URL 只保留首次出现
- ③ 内容去重：通过 MD5 指纹识别相同内容的不同来源

为什么需要内容指纹去重：
- 网上内容经常被转载，URI 不同但内容完全相同
- 去重可降低后续 LLM 分析成本，避免给 AI 喂入冗余信息
"""

import hashlib
import logging
from typing import List, Set
from app.schemas.agent import CleanerInput, CleanedItem, CleanerOutput, CollectedItem

logger = logging.getLogger(__name__)

class CleanerAgent:
    def __init__(self, min_content_length: int = 20, max_chunk_size: int = 1000):
        """
        min_content_length: 内容最短阈值（字符），低于此长度的条目丢弃
        max_chunk_size: 文本分块大小，用于生成便于 LLM 处理的上下文块
        """
        self.min_content_length = min_content_length
        self.max_chunk_size = max_chunk_size

    def _get_content_fingerprint(self, text: str) -> str:
        """对规范化文本计算 MD5 哈希，用于精确去重"""
        normalized = "".join(text.split()).lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _chunk_text(self, text: str) -> List[str]:
        """
        将文本按 max_chunk_size 分块
        尽可能在换行处断句，保持语义完整性
        """
        lines = text.split("\n")
        chunks, current_chunk = [], []
        current_len = 0

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if current_len + len(line_str) > self.max_chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line_str]
                current_len = len(line_str)
            else:
                current_chunk.append(line_str)
                current_len += len(line_str) + 1
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        return chunks

    async def execute(self, input_data: CleanerInput) -> CleanerOutput:
        """
        执行数据清洗流水线：
        ① 短内容过滤 → ② URI 去重 → ③ 内容指纹去重 → ④ 文本分块
        """
        logger.info(f"CleanerAgent started for task_id: {input_data.task_id}, processing {len(input_data.raw_items)} items")

        if not input_data.raw_items:
            return CleanerOutput(task_id=input_data.task_id, success=True, cleaned_items=[], total_removed=0)

        seen_uris: Set[str] = set()
        seen_fingerprints: Set[str] = set()
        cleaned_list: List[CleanedItem] = []
        removed_count = 0

        for item in input_data.raw_items:
            # ① 过滤过短的低质内容
            clean_text = item.content.strip()
            if len(clean_text) < self.min_content_length:
                removed_count += 1
                logger.debug(f"Removed item '{item.title}': too short ({len(clean_text)} chars)")
                continue

            # ② URI 去重：相同 URL 只保留首次出现
            if item.source_uri in seen_uris:
                removed_count += 1
                logger.debug(f"Removed item '{item.title}': duplicate URI {item.source_uri}")
                continue

            # ③ 内容指纹去重：不同 URL 但内容相同的条目也排除
            fingerprint = self._get_content_fingerprint(clean_text)
            if fingerprint in seen_fingerprints:
                removed_count += 1
                logger.debug(f"Removed item '{item.title}': duplicate content fingerprint")
                continue

            seen_uris.add(item.source_uri)
            seen_fingerprints.add(fingerprint)

            # ④ 文本分块（便于后续 LLM 阶段处理）
            chunks = self._chunk_text(clean_text)
            summary = clean_text[:200] + ("..." if len(clean_text) > 200 else "")

            cleaned_list.append(CleanedItem(
                source_type=item.source_type,
                source_uri=item.source_uri,
                title=item.title,
                summary=summary,
                content_chunks=chunks,
                relevance_score=1.0,
                metadata=item.metadata
            ))

        logger.info(f"CleanerAgent finished: kept {len(cleaned_list)}, removed {removed_count}")
        return CleanerOutput(
            task_id=input_data.task_id,
            success=True,
            cleaned_items=cleaned_list,
            total_removed=removed_count
        )
