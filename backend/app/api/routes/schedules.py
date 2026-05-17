from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.schemas.schedule import ScheduleCreate, ScheduleOut
from app.services.scheduler import SchedulerService

router = APIRouter()
scheduler_service = SchedulerService()

@router.post("", response_model=ResponseModel)
async def create_scheduled_job(
    sched: ScheduleCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    out = await scheduler_service.create_schedule(session, sched, current_user.id)
    return success_response(data=out.model_dump())

@router.get("", response_model=ResponseModel)
async def list_scheduled_jobs(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    lst = await scheduler_service.list_schedules(session, current_user.id)
    return success_response(data=[x.model_dump() for x in lst])

@router.post("/{task_id}/trigger", response_model=ResponseModel)
async def trigger_scheduled_job(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    ok = await scheduler_service.trigger_job(session, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Scheduled task not found or invalid trigger mode")
    return success_response(msg="Job triggered in background")

@router.delete("/{task_id}", response_model=ResponseModel)
async def delete_scheduled_job(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    ok = await scheduler_service.delete_schedule(session, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return success_response(msg="Scheduled task deleted")
