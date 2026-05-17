import asyncio
import logging
from typing import Any, Dict, Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.orchestrator import OrchestratorAgent
from app.schemas.agent import OrchestratorInput
from app.schemas.task import TaskCreate, TaskUpdate, TaskRunCreate
from app.services.task import TaskService

logger = logging.getLogger(__name__)

class TriggerService:
    def __init__(self):
        self.task_service = TaskService()

    async def run_qa_sync(self, session: AsyncSession, topic: str, max_items: int, user_id: int) -> Dict[str, Any]:
        # Create Task
        tc = TaskCreate(name=f"QA: {topic[:50]}", type="quick", trigger_mode="qa", input_data={"topic": topic, "max_items": max_items})
        task = await self.task_service.create_task(session, tc, user_id)
        
        recorded_runs = []
        async def state_cb(tid, st, err):
            recorded_runs.append((st, err))

        orch = OrchestratorAgent(state_callback=state_cb)
        req = OrchestratorInput(task_id=f"task-{task.id}", topic=topic, max_items=max_items)
        res = await orch.execute(req)
        
        # Update Task Status
        st = "completed" if res.status == "completed" else "failed"
        await self.task_service.update_task(session, task.id, TaskUpdate(status=st))
        
        return {
            "task_id": task.id,
            "status": st,
            "reporter_output": res.reporter_output.model_dump() if res.reporter_output else None,
            "recorded_runs": [r[0] for r in recorded_runs]
        }

    async def run_qa_stream(self, session: AsyncSession, topic: str, max_items: int, user_id: int) -> AsyncGenerator[str, None]:
        tc = TaskCreate(name=f"QA Stream: {topic[:50]}", type="quick", trigger_mode="qa", input_data={"topic": topic, "max_items": max_items})
        task = await self.task_service.create_task(session, tc, user_id)
        
        queue: asyncio.Queue = asyncio.Queue()

        async def state_cb(tid, st, err):
            await queue.put({"stage": st, "error": err, "task_id": task.id})

        async def pipeline_runner():
            try:
                orch = OrchestratorAgent(state_callback=state_cb)
                req = OrchestratorInput(task_id=f"task-{task.id}", topic=topic, max_items=max_items)
                res = await orch.execute(req)
                await queue.put({"stage": "done", "result": res.model_dump() if hasattr(res, 'model_dump') else res, "task_id": task.id})
            except Exception as e:
                logger.error(f"Pipeline runner error: {e}", exc_info=True)
                await queue.put({"stage": "failed", "error": str(e), "task_id": task.id})

        task_runner = asyncio.create_task(pipeline_runner())

        import json
        try:
            while True:
                msg = await queue.get()
                stage = msg.get("stage")
                error = msg.get("error")

                # DB updates
                if stage in ("collecting", "cleaning", "analyzing", "reporting"):
                    await self.task_service.create_task_run(session, TaskRunCreate(task_id=task.id, stage=stage, status="running"))
                elif stage in ("completed", "done"):
                    await self.task_service.update_task(session, task.id, TaskUpdate(status="completed"))
                elif stage == "failed":
                    await self.task_service.update_task(session, task.id, TaskUpdate(status="failed"))

                payload = json.dumps(msg, default=str)
                yield f"event: {stage}\ndata: {payload}\n\n"

                if stage in ("completed", "done", "failed"):
                    break
        except asyncio.CancelledError:
            logger.info(f"SSE Client disconnected for task {task.id}")
            task_runner.cancel()
            await self.task_service.update_task(session, task.id, TaskUpdate(status="cancelled"))
            raise
