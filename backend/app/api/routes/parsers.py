"""
文档解析 API 路由

提供文件上传、自动解析、附件持久化端点。

单文件 /upload 与批量 /batch-upload 共享 _upload_single() 内部助手，
避免两份几乎重复的逻辑。

持久化策略：
- 计算文件 sha256，与 user_id 组合作为去重键：相同内容复用旧 attachment
- 原始文件存入 MinIO（bucket: scdc-user-attachments，key: {user_id}/{uuid}/{filename}）
- 解析结果（content / chunks / metadata）落 attachments 表
- 失败时抛出 BusinessException，由全局异常处理器返回统一错误格式
"""

import io
import hashlib
import uuid
import asyncio
import logging
from typing import Any, List

from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import success_response, ResponseModel
from app.api.deps import get_current_active_user
from app.core.db import get_db
from app.core.exceptions import BusinessException
from app.models.attachment import Attachment
from app.models.user import User
from app.parsers.manager import ParserManager
from app.schemas.parser import ParseResult
from app.services.minio_client import minio_client

logger = logging.getLogger(__name__)

router = APIRouter()
parser_manager = ParserManager()


async def _upload_single(
    file: UploadFile,
    current_user: User,
    db: AsyncSession,
) -> dict:
    """处理单个文件的上传、哈希去重、MinIO 存储与解析持久化"""
    contents = await file.read()
    file_size = len(contents)
    file_hash = hashlib.sha256(contents).hexdigest()

    # 去重：相同 (user_id, hash) 复用旧记录
    existing = await db.execute(
        select(Attachment).where(
            Attachment.user_id == current_user.id,
            Attachment.file_hash == file_hash,
        )
    )
    row = existing.scalars().first()
    if row:
        return {
            "attachment_id": row.id,
            "filename": row.filename,
            "file_type": row.file_type,
            "file_size": row.file_size,
            "file_hash": row.file_hash,
            "parsed": True,
            "reused": True,
        }

    # 解析文件
    parse_result: ParseResult = await parser_manager.parse_file(
        io.BytesIO(contents), file.filename
    )

    # 持久化：生成 UUID，上传到 MinIO
    attachment_id = str(uuid.uuid4())
    object_key = f"{current_user.id}/{attachment_id}/{file.filename}"
    try:
        storage_ref = minio_client.put_object(
            object_key,
            io.BytesIO(contents),
            length=file_size,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as e:
        logger.warning(f"MinIO put_object failed for {object_key}: {e}")
        # 解析结果仍落库，便于后续手动恢复
        storage_ref = None

    attachment = Attachment(
        id=attachment_id,
        user_id=current_user.id,
        filename=file.filename,
        file_type=parse_result.file_type,
        file_size=file_size,
        file_hash=file_hash,
        minio_object_key=object_key,
        parsed_content=parse_result.content,
        parsed_chunks=[c.model_dump() for c in parse_result.chunks] if parse_result.chunks else None,
        extra_metadata={
            "storage_ref": storage_ref,
            **(parse_result.metadata or {}),
        },
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return {
        "attachment_id": attachment.id,
        "filename": attachment.filename,
        "file_type": attachment.file_type,
        "file_size": attachment.file_size,
        "file_hash": attachment.file_hash,
        "parsed": True,
        "reused": False,
    }


@router.post("/upload", response_model=ResponseModel)
async def upload_and_parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """上传单个文件，解析后持久化到 attachments 表，返回 attachment_id"""
    try:
        result = await _upload_single(file, current_user, db)
        return success_response(data=result)
    except BusinessException as e:
        raise e
    except Exception as e:
        logger.exception(f"upload_and_parse_file failed for {file.filename}")
        raise BusinessException(code=500, message=f"文件解析失败: {e}")


@router.post("/batch-upload", response_model=ResponseModel[dict])
async def batch_upload_and_parse(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """并发批量上传并解析多个文件，单文件失败不影响其他文件"""
    results = await asyncio.gather(
        *[_upload_single(file, current_user, db) for file in files],
        return_exceptions=True,
    )
    success = []
    failed = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            failed.append({"filename": files[i].filename, "error": str(r)})
        else:
            success.append(r)
    return success_response(data={
        "success": success,
        "failed": failed,
        "attachment_ids": [s["attachment_id"] for s in success],
    })
