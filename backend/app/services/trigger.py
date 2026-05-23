"""
任务触发服务

提供两种 AI 流水线触发方式：
- run_qa_sync(): 同步执行，等待完整结果后返回（适合普通 HTTP 请求）
- run_qa_stream(): SSE 流式执行，通过 Server-Sent Events 实时推送中间状态

核心流程：
1. 创建 Task 记录并持久化到数据库
2. 实例化 OrchestratorAgent 并传入 state_callback 追踪中间状态变化
3. 每次状态变化（collecting/cleaning/analyzing/reporting）写入 TaskRun 记录
4. 完成后更新 Task 状态为 completed/failed

为什么同时提供同步和流式：
- 同步：前端简单场景（如 Dashboard 快速搜索），一个请求完成查询
- 流式：前端需要实时进度展示（如进度条、阶段动画），增强用户体验
"""

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
        """
        同步执行 AI 流水线，等待全部阶段完成后返回结果

        参数:
            topic: 分析主题关键词
            max_items: 最大搜索和清洗条目数
            user_id: 发起请求的用户 ID
        返回:
            包含 task_id、status 和 reporter_output 的字典
        """
        tc = TaskCreate(name=f"QA: {topic[:50]}", type="quick", trigger_mode="qa", input_data={"topic": topic, "max_items": max_items})
        task = await self.task_service.create_task(session, tc, user_id)

        recorded_runs = []
        async def state_cb(tid, st, err):
            recorded_runs.append((st, err))

        orch = OrchestratorAgent(state_callback=state_cb)
        req = OrchestratorInput(task_id=f"task-{task.id}", topic=topic, max_items=max_items)
        res = await orch.execute(req)

        st = "completed" if res.status == "completed" else "failed"
        await self.task_service.update_task(session, task.id, TaskUpdate(status=st))

        return {
            "task_id": task.id,
            "status": st,
            "reporter_output": res.reporter_output.model_dump() if res.reporter_output else None,
            "recorded_runs": [r[0] for r in recorded_runs]
        }

    async def run_qa_stream(self, session: AsyncSession, topic: str, max_items: int, user_id: int) -> AsyncGenerator[str, None]:
        """
        SSE 流式执行 AI 流水线，实时推送阶段状态

        为什么使用 asyncio.Queue 进行协程间通信：
        - pipeline_runner 在后台任务中执行流水线
        - 主协程从 Queue 读取消息并 yield SSE 格式数据
        - Queue 天然线程安全，避免共享变量竞态

        SSE 事件类型：
        - collecting/cleaning/analyzing/reporting: 阶段进行中
        - done: 全部完成
        - failed: 流水线异常
        """
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
