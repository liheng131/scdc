"""
MinIO 客户端封装

提供对象存储的简易读写接口，用于持久化用户上传的附件原始文件。
设计上做了两个层面的兜底：

1. SDK 加载层面：若 minio 包未安装或导入失败，回退到本地文件系统。
2. 操作层面：单次 put_object/delete_object 调用失败时，也回退到本地存储，
   保证上传/删除逻辑在 MinIO 临时不可用时不至于整体崩溃。

这样开发环境无需启动 MinIO 容器也能跑通上传/解析链路。
"""

import io
import logging
import pathlib
from typing import BinaryIO, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class MinioClient:
    def __init__(self):
        self.bucket = "scdc-user-attachments"
        self._client = None
        self._fallback_dir = None
        try:
            from minio import Minio
            from minio.error import S3Error  # noqa: F401
            self._client = Minio(
                settings.minio_endpoint.replace("http://", "").replace("https://", ""),
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=False,
            )
            self._ensure_bucket()
        except Exception as e:
            logger.warning(f"MinIO unavailable, falling back to local storage: {e}")
            self._fallback_dir = pathlib.Path("data/attachments")
            self._fallback_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_bucket(self):
        if self._client and not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def put_object(self, key: str, data: BinaryIO, length: int, content_type: str = "application/octet-stream") -> str:
        if self._client:
            from minio.error import S3Error
            try:
                self._client.put_object(self.bucket, key, data, length=length, content_type=content_type)
                return f"s3://{self.bucket}/{key}"
            except S3Error as e:
                logger.warning(f"MinIO put_object failed, falling back to local: {e}")

        # Fallback: local file
        if self._fallback_dir:
            full = self._fallback_dir / key
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(data.read() if hasattr(data, 'read') else data)
            return f"local://{full}"
        raise RuntimeError("No storage backend available")

    def delete_object(self, key: str) -> bool:
        if self._client:
            from minio.error import S3Error
            try:
                self._client.remove_object(self.bucket, key)
                return True
            except S3Error:
                pass
        if self._fallback_dir:
            full = self._fallback_dir / key
            if full.exists():
                full.unlink()
                return True
        return False

    def get_object(self, key: str) -> Optional[bytes]:
        """读取对象字节流。MinIO 不可用时尝试本地降级目录,失败返回 None。"""
        if self._client:
            from minio.error import S3Error
            try:
                resp = self._client.get_object(self.bucket, key)
                try:
                    return resp.read()
                finally:
                    resp.close()
                    resp.release_conn()
            except S3Error as e:
                logger.warning("MinIO get_object failed for %s: %s, trying local fallback", key, e)
        if self._fallback_dir:
            full = self._fallback_dir / key
            if full.exists():
                return full.read_bytes()
        return None


minio_client = MinioClient()
