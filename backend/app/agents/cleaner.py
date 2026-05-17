import hashlib
import logging
from typing import List, Set
from app.schemas.agent import CleanerInput, CleanedItem, CleanerOutput, CollectedItem

logger = logging.getLogger(__name__)

class CleanerAgent:
    def __init__(self, min_content_length: int = 20, max_chunk_size: int = 1000):
        self.min_content_length = min_content_length
        self.max_chunk_size = max_chunk_size

    def _get_content_fingerprint(self, text: str) -> str:
        # Simple md5 hash of normalized text for exact deduplication
        normalized = "".join(text.split()).lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _chunk_text(self, text: str) -> List[str]:
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
        logger.info(f"CleanerAgent started for task_id: {input_data.task_id}, processing {len(input_data.raw_items)} items")

        if not input_data.raw_items:
            return CleanerOutput(task_id=input_data.task_id, success=True, cleaned_items=[], total_removed=0)

        seen_uris: Set[str] = set()
        seen_fingerprints: Set[str] = set()
        cleaned_list: List[CleanedItem] = []
        removed_count = 0

        for item in input_data.raw_items:
            # Filter low quality content
            clean_text = item.content.strip()
            if len(clean_text) < self.min_content_length:
                removed_count += 1
                logger.debug(f"Removed item '{item.title}': too short ({len(clean_text)} chars)")
                continue

            # Deduplicate by URI
            if item.source_uri in seen_uris:
                removed_count += 1
                logger.debug(f"Removed item '{item.title}': duplicate URI {item.source_uri}")
                continue

            # Deduplicate by content fingerprint
            fingerprint = self._get_content_fingerprint(clean_text)
            if fingerprint in seen_fingerprints:
                removed_count += 1
                logger.debug(f"Removed item '{item.title}': duplicate content fingerprint")
                continue

            seen_uris.add(item.source_uri)
            seen_fingerprints.add(fingerprint)

            # Generate chunks
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
