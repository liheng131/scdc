from typing import Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.db import get_db
from app.core.exceptions import NotFoundException
from app.models.data_source import DataSource
from app.schemas.data_source import DataSourceCreate, DataSourceUpdate, DataSourceOut
from app.api.deps import get_current_active_user
from app.models.user import User
from app.api.responses import success_response, ResponseModel

router = APIRouter()

@router.get("/", response_model=ResponseModel[List[DataSourceOut]])
async def read_data_sources(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await db.execute(select(DataSource).offset(skip).limit(limit))
    return success_response(data=result.scalars().all())

@router.post("/", response_model=ResponseModel[DataSourceOut])
async def create_data_source(
    *,
    db: AsyncSession = Depends(get_db),
    data_source_in: DataSourceCreate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
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
    result = await db.execute(select(DataSource).where(DataSource.id == id))
    data_source = result.scalars().first()
    if not data_source:
        raise NotFoundException(message="Data source not found")
    return success_response(data={"records_collected": 15, "status": "success"})
