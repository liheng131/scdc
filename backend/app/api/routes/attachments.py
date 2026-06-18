"""
附件（Attachments）管理 API 路由

提供附件的查询、详情、删除等接口，供前端附件管理界面与采集 Agent 使用。

设计要点：
- 列表查询按用户隔离，仅返回当前登录用户的附件
- 列表默认按 created_at 倒序，limit 默认 50
- DELETE 接口会同时清理 MinIO 中的对象，保证存储与数据库一致性
- POST /batch 用于 CollectorAgent 按 ID 批量拉取已解析的附件内容
"""

import logging
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import NotFoundException
from app.models.attachment import Attachment
from app.schemas.attachment import AttachmentOut
from app.api.deps import get_current_active_user
from app.models.user import User
from app.api.responses import success_response, ResponseModel
from app.services.minio_client import minio_client

logger = logging.getLogger(__name__)

router = APIRouter()


class AttachmentBatchRequest(BaseModel):
    ids: List[str]


@router.get("", response_model=ResponseModel[List[AttachmentOut]])
async def list_attachments(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """列出当前用户的所有附件（按创建时间倒序）"""
    result = await db.execute(
        select(Attachment)
        .where(Attachment.user_id == current_user.id)
        .order_by(Attachment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = result.scalars().all()
    return success_response(data=[AttachmentOut.model_validate(x).model_dump() for x in items])


@router.post("/batch", response_model=ResponseModel[List[AttachmentOut]])
async def get_attachments_batch(
    req: AttachmentBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """按 ID 列表批量获取当前用户的附件（供 CollectorAgent 使用）"""
    if not req.ids:
        return success_response(data=[])
    result = await db.execute(
        select(Attachment)
        .where(Attachment.user_id == current_user.id, Attachment.id.in_(req.ids))
    )
    items = result.scalars().all()
    return success_response(data=[AttachmentOut.model_validate(x).model_dump() for x in items])


@router.get("/{attachment_id}", response_model=ResponseModel[AttachmentOut])
async def get_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """获取单个附件详情"""
    result = await db.execute(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.user_id == current_user.id,
        )
    )
    attachment = result.scalars().first()
    if not attachment:
        raise NotFoundException(message="附件不存在")
    return success_response(data=AttachmentOut.model_validate(attachment).model_dump())


@router.delete("/{attachment_id}", response_model=ResponseModel)
async def delete_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """删除附件（同时清理 MinIO 对象）"""
    result = await db.execute(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.user_id == current_user.id,
        )
    )
    attachment = result.scalars().first()
    if not attachment:
        raise NotFoundException(message="附件不存在")

    # 先删 MinIO 对象（删除失败不阻塞 DB 记录清理）
    try:
        minio_client.delete_object(attachment.minio_object_key)
    except Exception as e:
        logger.warning(f"删除 MinIO 对象失败 {attachment.minio_object_key}: {e}")

    await db.delete(attachment)
    await db.commit()
    return success_response(msg="Attachment deleted")
