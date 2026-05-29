"""
Milvus 向量存储服务

封装 pymilvus 客户端，提供向量集合管理、插入、搜索与删除功能。
连接失败时不会抛出异常，仅记录警告日志。
"""

import logging
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility
from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "scdc_reports"


class VectorStoreService:
    """Milvus 向量存储服务单例"""

    def __init__(self):
        self._connected = False
        self._collection = None
        try:
            connections.connect(alias="default", uri=settings.milvus_url, timeout=5)
            self._connected = True
            logger.info("Connected to Milvus at %s", settings.milvus_url)
        except Exception as e:
            logger.warning("Failed to connect to Milvus at %s: %s", settings.milvus_url, e)

    def _ensure_connected(self):
        if not self._connected:
            raise RuntimeError("Milvus is not connected")

    def collection_exists(self) -> bool:
        if not self._connected:
            logger.warning("Milvus not connected, cannot check collection existence")
            return False
        return utility.has_collection(COLLECTION_NAME)

    def init_collection(self, dim: int):
        self._ensure_connected()
        if self._collection is not None:
            return
        if utility.has_collection(COLLECTION_NAME):
            logger.info("Collection '%s' already exists, loading...", COLLECTION_NAME)
            self._collection = Collection(COLLECTION_NAME)
            return
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="report_id", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="chunk_idx", dtype=DataType.INT64),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields, description="SCDC reports vector store")
        self._collection = Collection(name=COLLECTION_NAME, schema=schema)
        index_params = {
            "metric_type": "COSINE",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        }
        self._collection.create_index(field_name="vector", index_params=index_params)
        logger.info("Created collection '%s' with dim=%d", COLLECTION_NAME, dim)

    def insert(self, report_id: str, chunks: list[str], vectors: list[list[float]]):
        self._ensure_connected()
        if self._collection is None:
            self._collection = Collection(COLLECTION_NAME)
        n = len(chunks)
        data = [
            [report_id] * n,
            list(range(n)),
            chunks,
            vectors,
        ]
        self._collection.insert(data)
        self._collection.flush()
        logger.info("Inserted %d chunks for report '%s'", n, report_id)

    def search(self, query_vector: list[float], top_k: int = 3, filter_expr: str | None = None) -> list[dict]:
        self._ensure_connected()
        if self._collection is None:
            self._collection = Collection(COLLECTION_NAME)
        self._collection.load()
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        results = self._collection.search(
            [query_vector],
            "vector",
            search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=["report_id", "chunk_idx", "text"],
        )
        hits = []
        for hits_list in results:
            for hit in hits_list:
                hits.append({
                    "id": hit.id,
                    "report_id": hit.entity.get("report_id"),
                    "chunk_idx": hit.entity.get("chunk_idx"),
                    "text": hit.entity.get("text"),
                    "score": hit.score,
                })
        return hits

    def delete_by_report(self, report_id: str):
        self._ensure_connected()
        if self._collection is None:
            self._collection = Collection(COLLECTION_NAME)
        expr = f'report_id == "{report_id}"'
        self._collection.delete(expr)
        logger.info("Deleted vectors for report '%s'", report_id)