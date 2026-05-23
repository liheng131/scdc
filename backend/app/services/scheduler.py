"""
定时任务调度服务

提供基于 Cron 表达式的定时任务创建、管理和执行调度。

核心流程：
1. SchedulerService._scheduler_loop() 每分钟扫描一次数据库中 status=scheduled 的任务
2. match_cron() 比对当前时间与 Cron 表达式是否匹配
3. 匹配时调用 trigger_job() 异步执行 OrchestratorAgent 流水线

为什么使用独立的调度循环而不是 Celery/APScheduler：
- 调度器集成在 FastAPI 进程内（通过 lifespan），减少部署复杂度
- 避免引入额外的消息队列依赖（Redis/RabbitMQ）
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task
from app.schemas.schedule import ScheduleCreate, ScheduleOut
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task import TaskService
from app.agents.orchestrator import OrchestratorAgent
from app.schemas.agent import OrchestratorInput

logger = logging.getLogger(__name__)

def match_cron(cron_str: str, dt: datetime) -> bool:
    """
    判断给定时间是否匹配 Cron 表达式

    支持标准 5 字段 Cron 格式（分 时 日 月 星期），
    支持 * 通配符、/ 步进、, 枚举三种语法。
    """
    parts = cron_str.strip().split()
    if len(parts) != 5:
        return False

    def match_part(part: str, val: int) -> bool:
        if part == "*":
            return True
        if "/" in part:
            _, step = part.split("/")
            return val % int(step) == 0
        if "," in part:
            return str(val) in part.split(",")
        return str(val) == part

    return (match_part(parts[0], dt.minute) and
            match_part(parts[1], dt.hour) and
            match_part(parts[2], dt.day) and
            match_part(parts[3], dt.month) and
            match_part(parts[4], dt.weekday()))

class SchedulerService:
    def __init__(self, async_session_factory=None):
        self.task_service = TaskService()
        self.async_session_factory = async_session_factory
        self.running = False
        self.task_loop = None

    async def create_schedule(self, session: AsyncSession, sched: ScheduleCreate, user_id: int) -> ScheduleOut:
        tc = TaskCreate(
            name=sched.name,
            type="scheduled",
            trigger_mode="schedule",
            input_data={"cron": sched.cron_expr, "topic": sched.topic, "max_items": sched.max_items}
        )
        task = await self.task_service.create_task(session, tc, user_id)
        await self.task_service.update_task(session, task.id, TaskUpdate(status="scheduled"))
        return ScheduleOut(
            task_id=task.id,
            name=task.name,
            cron_expr=sched.cron_expr,
            topic=sched.topic,
            status="scheduled"
        )

    async def list_schedules(self, session: AsyncSession, user_id: int) -> List[ScheduleOut]:
        tasks = await self.task_service.list_tasks(session, user_id=user_id)
        schedules = []
        for t in tasks:
            if t.trigger_mode == "schedule" and t.status != "deleted":
                cron = t.input_data.get("cron", "")
                topic = t.input_data.get("topic", "")
                schedules.append(ScheduleOut(
                    task_id=t.id,
                    name=t.name,
                    cron_expr=cron,
                    topic=topic,
                    status=t.status
                ))
        return schedules

    async def delete_schedule(self, session: AsyncSession, task_id: int) -> bool:
        return await self.task_service.delete_task(session, task_id)

    async def trigger_job(self, session: AsyncSession, task_id: int) -> bool:
        """
        触发一个定时任务执行

        为什么使用 asyncio.create_task 后台执行：
        - OrchestratorAgent 流水线执行时间可能很长（LLM 调用可达数十秒）
        - 不阻塞调度循环，允许同时执行多个定时任务
        """
        task = await self.task_service.get_task(session, task_id)
        if not task or task.trigger_mode != "schedule":
            return False

        await self.task_service.update_task(session, task_id, TaskUpdate(status="running"))
        topic = task.input_data.get("topic", "")
        max_items = task.input_data.get("max_items", 3)

        async def run_bg():
            try:
                orch = OrchestratorAgent()
                req = OrchestratorInput(task_id=f"sched-{task_id}", topic=topic, max_items=max_items)
                res = await orch.execute(req)
                st = "completed" if res.status == "completed" else "failed"
            except Exception as e:
                logger.error(f"Scheduled job {task_id} failed: {e}", exc_info=True)
                st = "failed"

            if self.async_session_factory:
                async with self.async_session_factory() as s:
                    await self.task_service.update_task(s, task_id, TaskUpdate(status=st))
            else:
                await self.task_service.update_task(session, task_id, TaskUpdate(status=st))

        asyncio.create_task(run_bg())
        return True

    def start_loop(self):
        """启动调度循环，由 FastAPI lifespan 调用"""
        if not self.running and self.async_session_factory:
            self.running = True
            self.task_loop = asyncio.create_task(self._scheduler_loop())
            logger.info("Scheduler loop started.")

    def stop_loop(self):
        """停止调度循环，优雅退出"""
        if self.running:
            self.running = False
            if self.task_loop:
                self.task_loop.cancel()
            logger.info("Scheduler loop stopped.")

    async def _scheduler_loop(self):
        """
        调度器主循环，每 60 秒扫描一次到期任务

        为什么 60 秒间隔：
        - Cron 最小粒度是分钟级，60 秒轮询不会遗漏
        - 较长的间隔降低数据库查询频率
        """
        while self.running:
            try:
                now = datetime.utcnow()
                async with self.async_session_factory() as s:
                    stmt = select(Task).where(Task.trigger_mode == "schedule").where(Task.status == "scheduled")
                    res = await s.execute(stmt)
                    tasks = res.scalars().all()

                    for t in tasks:
                        cron = t.input_data.get("cron", "")
                        if match_cron(cron, now):
                            logger.info(f"Cron matched for task {t.id} ({cron}) at {now}")
                            await self.trigger_job(s, t.id)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            await asyncio.sleep(60)
