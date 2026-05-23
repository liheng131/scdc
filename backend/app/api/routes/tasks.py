"""
分析任务（Tasks）API 路由

提供任务 CRUD、任务运行记录管理、手动触发运行等端点。

权限设计：
- 管理员可查看所有任务
- 普通用户只能查看和操作自己创建的任务
- 所有端点均需登录认证
"""

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_user, get_db
from app.api.responses import success_response, ResponseModel
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut, TaskRunCreate, TaskRunUpdate, TaskRunOut
from app.services.task import TaskService

router = APIRouter()
task_service = TaskService()

@router.post("", response_model=ResponseModel[TaskOut])
async def create_task(
    request: TaskCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """创建新的分析任务"""
    task = await task_service.create_task(session, request, current_user.id)
    return success_response(data=task)

@router.get("", response_model=ResponseModel[List[TaskOut]])
async def list_tasks(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """获取任务列表：管理员看全部，普通用户只看自己的"""
    user_filter = current_user.id if current_user.role != "admin" else None
    tasks = await task_service.list_tasks(session, user_id=user_filter, skip=skip, limit=limit)
    return success_response(data=tasks)

@router.get("/{task_id}", response_model=ResponseModel[TaskOut])
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """获取单个任务详情（非管理员或非创建者返回 403）"""
    task = await task_service.get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return success_response(data=task)

@router.put("/{task_id}", response_model=ResponseModel[TaskOut])
async def update_task(
    task_id: int,
    request: TaskUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """更新任务配置"""
    task = await task_service.get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    updated = await task_service.update_task(session, task_id, request)
    return success_response(data=updated)

@router.delete("/{task_id}", response_model=ResponseModel[bool])
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """删除任务"""
    task = await task_service.get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    success = await task_service.delete_task(session, task_id)
    return success_response(data=success)

@router.post("/{task_id}/runs", response_model=ResponseModel[TaskRunOut])
async def create_task_run(
    task_id: int,
    request: TaskRunCreate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """为任务创建一次运行记录"""
    task = await task_service.get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and task.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    if request.task_id != task_id:
        raise HTTPException(status_code=400, detail="Task ID mismatch")
    run = await task_service.create_task_run(session, request)
    return success_response(data=run)

@router.post("/{task_id}/run", response_model=ResponseModel)
async def trigger_task_run(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db)
) -> Any:
    """手动触发一次任务执行（立即创建一个 collecting 状态的运行记录）"""
    task = await task_service.get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    run_req = TaskRunCreate(task_id=task_id, stage="collecting", status="running")
    run = await task_service.create_task_run(session, run_req)
    return success_response(data={"run_id": run.id, "status": run.status})
