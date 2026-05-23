"""
采集记录（Collected Records）管理 API 路由

提供采集记录的 CRUD 操作，按数据源查询记录列表。
"""

import logging
from typing import Any, List
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import NotFoundException
from app.models.collected_record import CollectedRecord
from app.schemas.collected_record import (
    CollectedRecordCreate, CollectedRecordUpdate, CollectedRecordOut,
)
from app.api.deps import get_current_active_user
from app.models.user import User
from app.api.responses import success_response, ResponseModel
from app.crawlers.http_crawler import HTTPCrawler
from app.schemas.crawler import CrawlRequest

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{data_source_id}/records", response_model=ResponseModel[List[CollectedRecordOut]])
async def list_records(
    data_source_id: int,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """获取指定数据源下的所有采集记录"""
    result = await db.execute(
        select(CollectedRecord)
        .where(CollectedRecord.data_source_id == data_source_id)
        .order_by(CollectedRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return success_response(data=result.scalars().all())

@router.post("/{data_source_id}/records", response_model=ResponseModel[CollectedRecordOut])
async def create_record(
    data_source_id: int,
    record_in: CollectedRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """为指定数据源新增一条采集记录"""
    record = CollectedRecord(data_source_id=data_source_id, **record_in.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return success_response(data=record)

@router.put("/{data_source_id}/records/{record_id}", response_model=ResponseModel[CollectedRecordOut])
async def update_record(
    data_source_id: int,
    record_id: int,
    record_in: CollectedRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """更新指定采集记录"""
    result = await db.execute(
        select(CollectedRecord).where(
            CollectedRecord.id == record_id,
            CollectedRecord.data_source_id == data_source_id,
        )
    )
    record = result.scalars().first()
    if not record:
        raise NotFoundException(message="采集记录不存在")

    update_data = record_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    db.add(record)
    await db.commit()
    await db.refresh(record)
    return success_response(data=record)

@router.delete("/{data_source_id}/records/{record_id}", response_model=ResponseModel[CollectedRecordOut])
async def delete_record(
    data_source_id: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """删除指定采集记录"""
    result = await db.execute(
        select(CollectedRecord).where(
            CollectedRecord.id == record_id,
            CollectedRecord.data_source_id == data_source_id,
        )
    )
    record = result.scalars().first()
    if not record:
        raise NotFoundException(message="采集记录不存在")

    await db.delete(record)
    await db.commit()
    return success_response(data=record)

@router.post("/{data_source_id}/records/{record_id}/fetch-content", response_model=ResponseModel[CollectedRecordOut])
async def fetch_record_content(
    data_source_id: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    抓取指定记录的正文内容

    爬取记录中的 URL，提取正文文本并存入 content 字段。
    为什么单独提供这个端点而不是同步时一起抓取：
    - 同步时批量爬取所有链接的全文太耗时（每个 URL 需要 3-10 秒）
    - 用户可以选择性抓取感兴趣的文章，避免浪费资源
    """
    result = await db.execute(
        select(CollectedRecord).where(
            CollectedRecord.id == record_id,
            CollectedRecord.data_source_id == data_source_id,
        )
    )
    record = result.scalars().first()
    if not record:
        raise NotFoundException(message="采集记录不存在")

    if not record.url:
        return success_response(data={
            "records_collected": 0,
            "status": "no_url",
            "error": "该记录没有 URL，无法抓取正文",
        })

    try:
        crawler = HTTPCrawler()
        crawl_result = await crawler.crawl(CrawlRequest(
            url=record.url,
            force_clean=True,
            timeout=30,
        ))

        if crawl_result.success and crawl_result.clean_text:
            record.content = crawl_result.clean_text[:10000]
            record.title = crawl_result.title or record.title
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return success_response(data=record)
        else:
            return success_response(data={
                "records_collected": 0,
                "status": "crawl_failed",
                "error": crawl_result.error or "无法抓取正文",
            })
    except Exception as e:
        logger.warning(f"抓取记录 {record_id} 正文失败: {str(e)}")
        return success_response(data={
            "records_collected": 0,
            "status": "fetch_error",
            "error": str(e)[:200],
        })