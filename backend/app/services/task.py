import logging
from datetime import datetime
from typing import Optional, List, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.task import Task, TaskRun
from app.schemas.task import TaskCreate, TaskUpdate, TaskRunCreate, TaskRunUpdate

logger = logging.getLogger(__name__)

class TaskService:
    async def get_task(self, session: AsyncSession, task_id: int) -> Optional[Task]:
        stmt = select(Task).options(selectinload(Task.runs)).where(Task.id == task_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_task(self, session: AsyncSession, task_in: TaskCreate, user_id: int) -> Task:
        task = Task(
            name=task_in.name,
            type=task_in.type,
            trigger_mode=task_in.trigger_mode,
            status="created",
            input_data=task_in.input_data,
            output_ref=task_in.output_ref,
            created_by=user_id
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        logger.info(f"Task created: {task.id} by user {user_id}")
        return await self.get_task(session, task.id)

    async def list_tasks(self, session: AsyncSession, user_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> Sequence[Task]:
        stmt = select(Task).options(selectinload(Task.runs)).offset(skip).limit(limit).order_by(Task.id.desc())
        if user_id is not None:
            stmt = stmt.where(Task.created_by == user_id)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def update_task(self, session: AsyncSession, task_id: int, task_up: TaskUpdate) -> Optional[Task]:
        task = await self.get_task(session, task_id)
        if not task:
            return None
        
        update_data = task_up.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)
        
        await session.commit()
        logger.info(f"Task updated: {task.id}")
        return await self.get_task(session, task.id)

    async def delete_task(self, session: AsyncSession, task_id: int) -> bool:
        task = await self.get_task(session, task_id)
        if not task:
            return False
        await session.delete(task)
        await session.commit()
        logger.info(f"Task deleted: {task_id}")
        return True

    async def create_task_run(self, session: AsyncSession, run_in: TaskRunCreate) -> TaskRun:
        run = TaskRun(
            task_id=run_in.task_id,
            stage=run_in.stage,
            status=run_in.status,
            started_at=datetime.utcnow()
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        logger.info(f"TaskRun created: {run.id} for task {run.task_id} ({run.stage})")
        return run

    async def update_task_run(self, session: AsyncSession, run_id: int, run_up: TaskRunUpdate) -> Optional[TaskRun]:
        stmt = select(TaskRun).where(TaskRun.id == run_id)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            return None
        
        up_data = run_up.model_dump(exclude_unset=True)
        for field, val in up_data.items():
            setattr(run, field, val)
        
        await session.commit()
        await session.refresh(run)
        logger.info(f"TaskRun updated: {run.id} (status: {run.status})")
        return run
