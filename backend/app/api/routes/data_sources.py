"""
数据源（Data Sources）管理 API 路由

提供数据源的完整 CRUD 操作 + 手动同步触发端点。
所有端点均需要认证（get_current_active_user）。

数据源定义了从哪些渠道采集市场信息（搜索、爬虫、文档上传等）。
"""

import logging
from typing import Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from bs4 import BeautifulSoup

from app.core.db import get_db
from app.core.exceptions import NotFoundException
from app.models.data_source import DataSource
from app.models.collected_record import CollectedRecord
from app.schemas.data_source import DataSourceCreate, DataSourceUpdate, DataSourceOut
from app.api.deps import get_current_active_user
from app.models.user import User
from app.api.responses import success_response, ResponseModel
from app.crawlers.http_crawler import HTTPCrawler
from app.schemas.crawler import CrawlRequest

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=ResponseModel[List[DataSourceOut]])
async def read_data_sources(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """获取数据源列表，支持分页（skip/limit）"""
    result = await db.execute(select(DataSource).offset(skip).limit(limit))
    return success_response(data=result.scalars().all())

@router.post("/", response_model=ResponseModel[DataSourceOut])
async def create_data_source(
    *,
    db: AsyncSession = Depends(get_db),
    data_source_in: DataSourceCreate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """创建新的数据源"""
    data_source = DataSource(**data_source_in.model_dump())
    db.add(data_source)
    await db.commit()
    await db.refresh(data_source)
    return success_response(data=data_source)

@router.get("/{id}", response_model=ResponseModel[DataSourceOut])
async def read_data_source(
    *,
    db: AsyncSession = Depends(get_db),
    id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """根据 ID 获取单个数据源详情"""
    result = await db.execute(select(DataSource).where(DataSource.id == id))
    data_source = result.scalars().first()
    if not data_source:
        raise NotFoundException(message="Data source not found")
    return success_response(data=data_source)

@router.put("/{id}", response_model=ResponseModel[DataSourceOut])
async def update_data_source(
    *,
    db: AsyncSession = Depends(get_db),
    id: int,
    data_source_in: DataSourceUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """更新指定数据源的配置（部分更新，exclude_unset=True 只更新传入的字段）"""
    result = await db.execute(select(DataSource).where(DataSource.id == id))
    data_source = result.scalars().first()
    if not data_source:
        raise NotFoundException(message="Data source not found")

    update_data = data_source_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(data_source, field, value)

    db.add(data_source)
    await db.commit()
    await db.refresh(data_source)
    return success_response(data=data_source)

@router.delete("/{id}", response_model=ResponseModel[DataSourceOut])
async def delete_data_source(
    *,
    db: AsyncSession = Depends(get_db),
    id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """删除指定数据源"""
    result = await db.execute(select(DataSource).where(DataSource.id == id))
    data_source = result.scalars().first()
    if not data_source:
        raise NotFoundException(message="Data source not found")

    await db.delete(data_source)
    await db.commit()
    return success_response(data=data_source)

@router.post("/{id}/sync", response_model=ResponseModel)
async def sync_data_source(
    *,
    db: AsyncSession = Depends(get_db),
    id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    手动触发数据源同步

    根据数据源类型执行不同采集策略：
    - web: 爬取目标 URL，提取页面中的文章标题链接作为采集记录
    - api: 调用 API 接口获取数据（预留）
    - rss: 解析 RSS XML 获取条目（预留）

    为什么提取 <a> 标签中的链接而非全文：
    - 目标页面（如资讯列表页）通常包含 10-50 条标题链接
    - 一次性爬取所有链接的全文过于耗时，用户可在后续按需触发
    - 每条记录保存后可通过"查看"功能加载正文
    """
    result = await db.execute(select(DataSource).where(DataSource.id == id))
    data_source = result.scalars().first()
    if not data_source:
        raise NotFoundException(message="Data source not found")

    config = data_source.config or {}
    url = config.get("url", "")

    if not url:
        return success_response(data={"records_collected": 0, "status": "no_url"})

    source_type = data_source.type or "web"
    record_count = 0

    try:
        if source_type == "web":
            # 爬取目标页面，提取标题链接
            crawler = HTTPCrawler()
            crawl_result = await crawler.crawl(CrawlRequest(
                url=url,
                force_clean=False,
                timeout=30,
            ))

            if not crawl_result.success:
                return success_response(data={
                    "records_collected": 0,
                    "status": "crawl_failed",
                    "error": crawl_result.error or "无法访问目标页面",
                })

            if crawl_result.raw_html:
                soup = BeautifulSoup(crawl_result.raw_html, "html.parser")
                existing_urls = set()

                # 查询已有记录避免重复
                old_result = await db.execute(
                    select(CollectedRecord.url).where(CollectedRecord.data_source_id == id)
                )
                for row in old_result.scalars().all():
                    if row:
                        existing_urls.add(row)

                # 提取页面中所有 <a> 标签，过滤出有效文章链接
                for a_tag in soup.find_all("a", href=True):
                    title = a_tag.get_text(strip=True)
                    href = a_tag["href"]

                    if not title or len(title) < 4:
                        continue

                    # 处理相对路径
                    from urllib.parse import urljoin
                    full_url = urljoin(url, href)

                    if full_url in existing_urls:
                        continue

                    record = CollectedRecord(
                        data_source_id=id,
                        title=title[:500],
                        url=full_url,
                        source_type=source_type,
                    )
                    db.add(record)
                    existing_urls.add(full_url)
                    record_count += 1

                    # 限制每次最多采集 50 条
                    if record_count >= 50:
                        break

                await db.commit()

        elif source_type == "rss":
            crawler = HTTPCrawler()
            crawl_result = await crawler.crawl(CrawlRequest(
                url=url,
                force_clean=False,
                timeout=30,
            ))

            if not crawl_result.success:
                return success_response(data={
                    "records_collected": 0,
                    "status": "crawl_failed",
                    "error": crawl_result.error or "无法访问 RSS 源",
                })

            if crawl_result.raw_html:
                from xml.etree import ElementTree as ET
                soup = BeautifulSoup(crawl_result.raw_html, "xml")
                from urllib.parse import urljoin

                existing_urls = set()
                old_result = await db.execute(
                    select(CollectedRecord.url).where(CollectedRecord.data_source_id == id)
                )
                for row in old_result.scalars().all():
                    if row:
                        existing_urls.add(row)

                for item in soup.find_all("item"):
                    title_tag = item.find("title")
                    link_tag = item.find("link")

                    title = title_tag.get_text(strip=True) if title_tag else ""
                    link = link_tag.get_text(strip=True) if link_tag else (link_tag.get("href", "") if link_tag else "")

                    if not title or not link or link in existing_urls:
                        continue

                    record = CollectedRecord(
                        data_source_id=id,
                        title=title[:500],
                        url=link,
                        source_type=source_type,
                    )
                    db.add(record)
                    existing_urls.add(link)
                    record_count += 1

                await db.commit()

        else:
            return success_response(data={
                "records_collected": 0,
                "status": f"unsupported_type_{source_type}"
            })

    except Exception as e:
        logger.warning(f"数据源 {id} 同步失败: {str(e)}")
        return success_response(data={
            "records_collected": record_count,
            "status": "partial_error",
            "error": str(e)[:200],
        })

    return success_response(data={
        "records_collected": record_count,
        "status": "success",
    })
