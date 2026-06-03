"""
智能体工作流引擎

提供简化的市场洞察工作流执行。
状态流: idle → running(收集→清洗→分析→报告) → completed

前端以对话形式展示，仅显示最终报告结果。
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional, AsyncGenerator

from sqlalchemy import select, update
from app.core.db import async_session_factory
from app.models.workflow_run import WorkflowRun
from app.agents.orchestrator import OrchestratorAgent
from app.schemas.agent import OrchestratorInput
from app.services.intent_classifier import IntentClassifier
from app.services.direct_response import DirectResponseService

logger = logging.getLogger(__name__)

STAGE_SEQUENCE = ["collecting", "cleaning", "analyzing", "reporting"]
STAGE_LABELS = {
    "collecting": "搜索信息",
    "cleaning": "整理数据",
    "analyzing": "分析洞察",
    "reporting": "生成报告",
}

STAGE_ICONS = {
    "collecting": "🔍",
    "cleaning": "🧹",
    "analyzing": "🧠",
    "reporting": "📝",
}

class WorkflowState:
    def __init__(self, workflow_id: str, topic: str, max_items: int, dimensions: list):
        self.workflow_id = workflow_id
        self.topic = topic
        self.max_items = max_items
        self.dimensions = dimensions
        self.current_stage = ""
        self.current_stage_index = -1
        self.status = "idle"
        self.error: Optional[str] = None
        self.stages: Dict[str, Any] = {}
        self.result: Optional[Dict[str, Any]] = None
        self.is_direct_response: bool = False

class WorkflowService:
    def __init__(self):
        self._workflows: Dict[str, WorkflowState] = {}
        self._intent_classifier = IntentClassifier()
        self._direct_response = DirectResponseService()

    async def _classify_intent(self, message: str, conversation_history: list = None, has_existing_report: bool = False) -> dict:
        return await self._intent_classifier.classify(message, conversation_history, has_existing_report)

    async def run_direct_response_stream(self, message: str, conversation_history: list = None) -> AsyncGenerator[str, None]:
        async for chunk in self._direct_response.generate_response_stream(message, conversation_history):
            yield chunk

    async def run_follow_up_stream(self, state: WorkflowState, message: str, conversation_history: list = None) -> AsyncGenerator[str, None]:
        """处理追问请求，在当前对话上下文中生成回复"""
        state.is_direct_response = True
        state.topic = message
        state.status = "running"
        state.current_stage = "follow_up"
        await self._persist_stage_update(state)

        yield self._sse("stage_start", {
            "stage": "follow_up",
            "label": "回复追问",
            "icon": "💬",
            "index": 0,
            "total": 1,
        })

        async for chunk in self._direct_response.generate_response_stream(
            message=message,
            conversation_history=conversation_history,
            workflow_id=state.workflow_id,
        ):
            yield chunk

        state.status = "completed"
        state.current_stage = ""
        await self._persist_stage_update(state)

        yield self._sse("stage_complete", {
            "stage": "follow_up",
            "label": "回复追问",
        })

    async def create_workflow(self, topic: str, max_items: int, dimensions: list = None) -> WorkflowState:
        wf_id = str(uuid.uuid4())[:8]
        if dimensions is None:
            dimensions = []
        state = WorkflowState(wf_id, topic, max_items, dimensions)
        self._workflows[wf_id] = state

        try:
            async with async_session_factory() as session:
                wf_run = WorkflowRun(
                    workflow_id=wf_id,
                    topic=topic,
                    status="idle",
                    current_stage="",
                    stages_json=json.dumps({}),
                )
                session.add(wf_run)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist workflow %s: %s", wf_id, e)

        return state

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        if workflow_id in self._workflows:
            return self._workflows[workflow_id]

        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)
                )
                wf_run = result.scalar_one_or_none()
                if wf_run:
                    state = WorkflowState(
                        workflow_id=wf_run.workflow_id,
                        topic=wf_run.topic,
                        max_items=0,
                        dimensions=[],
                    )
                    state.status = wf_run.status
                    state.current_stage = wf_run.current_stage
                    state.stages = json.loads(wf_run.stages_json) if wf_run.stages_json else {}
                    state.result = json.loads(wf_run.result_json) if wf_run.result_json else None
                    state.error = wf_run.error
                    self._workflows[workflow_id] = state
                    return state
        except Exception as e:
            logger.warning("Failed to load workflow %s from DB: %s", workflow_id, e)

        return None

    async def _persist_stage_update(self, state: WorkflowState):
        try:
            async with async_session_factory() as session:
                await session.execute(
                    update(WorkflowRun)
                    .where(WorkflowRun.workflow_id == state.workflow_id)
                    .values(
                        status=state.status,
                        current_stage=state.current_stage,
                        stages_json=json.dumps(state.stages),
                        result_json=json.dumps(state.result) if state.result else None,
                        error=state.error,
                    )
                )
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist stage update for %s: %s", state.workflow_id, e)

    async def run_workflow_stream(self, state: WorkflowState, start_stage: str = None, reentry_context: str = None) -> AsyncGenerator[str, None]:
        if state.is_direct_response:
            state.status = "running"
            state.current_stage = "direct_response"
            await self._persist_stage_update(state)

            async for chunk in self._direct_response.generate_response_stream(state.topic, workflow_id=state.workflow_id):
                yield chunk

            state.status = "completed"
            await self._persist_stage_update(state)
            return

        queue = asyncio.Queue()
        stage_idx_map = {s: i for i, s in enumerate(STAGE_SEQUENCE)}

        async def sse_callback(task_id, status, error):
            await queue.put((status, error))

        orch = OrchestratorAgent(state_callback=sse_callback)

        async def run_orch():
            return await orch.execute(OrchestratorInput(
                task_id=state.workflow_id,
                topic=state.topic,
                max_items=state.max_items,
                dimensions=state.dimensions,
                include_charts=True,
                start_stage=start_stage,
                reentry_context=reentry_context,
            ))

        task = asyncio.ensure_future(run_orch())
        prev_stage = ""

        try:
            while not task.done():
                try:
                    status, error = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if status == "failed":
                    state.status = "failed"
                    state.error = error
                    if prev_stage:
                        yield self._sse("stage_error", {
                            "stage": prev_stage, "label": STAGE_LABELS.get(prev_stage, prev_stage),
                            "error": error[:500] if error else "",
                        })
                    await self._persist_stage_update(state)
                    try:
                        await task
                    except Exception:
                        pass
                    return

                if status == "queued":
                    continue

                if status in STAGE_SEQUENCE:
                    if prev_stage and prev_stage in STAGE_SEQUENCE:
                        yield self._sse("stage_complete", {
                            "stage": prev_stage, "label": STAGE_LABELS[prev_stage],
                        })
                        state.current_stage = prev_stage
                        await self._persist_stage_update(state)

                    yield self._sse("stage_start", {
                        "stage": status, "label": STAGE_LABELS[status],
                        "icon": STAGE_ICONS[status],
                        "index": stage_idx_map.get(status, 0), "total": 4,
                    })
                    state.current_stage = status
                    prev_stage = status

            orch_output = await task

            if prev_stage:
                yield self._sse("stage_complete", {
                    "stage": prev_stage, "label": STAGE_LABELS.get(prev_stage, prev_stage),
                })

            state.status = "completed"
            reporter = orch_output.reporter_output
            state.result = {
                "report_markdown": reporter.markdown_report if reporter else "",
                "chart_configs": reporter.chart_configs if reporter else [],
                "chart_images": reporter.chart_images if reporter else [],
                "sections": [{"title": s.title, "content": s.content} for s in (reporter.sections if reporter else [])],
            }
            state.stages = {
                "collecting": {"item_count": orch_output.collected_count},
                "cleaning": {"before_count": orch_output.collected_count, "after_count": orch_output.cleaned_count},
                "analyzing": {"insight_count": len(orch_output.analyzer_output.insights) if orch_output.analyzer_output else 0},
                "reporting": state.result,
            }
            await self._persist_stage_update(state)

            report_data = state.result or {}

            report_id = None
            try:
                from app.services.report import ReportService
                from app.core.db import async_session_factory as db_session_factory
                from app.models.report import Report as ReportModel
                from sqlalchemy import select as sa_select

                report_svc = ReportService()
                async with db_session_factory() as sess:
                    existing = await sess.execute(
                        sa_select(ReportModel).where(ReportModel.task_id == state.workflow_id)
                    )
                    if not existing.scalar_one_or_none():
                        report = await report_svc.create_from_workflow(
                            sess,
                            task_id=state.workflow_id,
                            title=state.topic,
                            content_markdown=report_data.get("report_markdown", ""),
                            summary=report_data.get("report_markdown", "")[:200] if report_data.get("report_markdown") else None,
                            chart_images=report_data.get("chart_images", []),
                        )
                        report_id = report.id
                        logger.info("Auto-saved report for workflow %s, report_id=%s", state.workflow_id, report_id)
            except Exception as e:
                logger.warning("Failed to auto-save report for workflow %s: %s", state.workflow_id, e)

            yield self._sse("completed", {
                "workflow_id": state.workflow_id, "topic": state.topic,
                "report_markdown": report_data.get("report_markdown", ""),
                "chart_configs": report_data.get("chart_configs", []),
                "sections": report_data.get("sections", []),
                "collected_count": orch_output.collected_count,
                "cleaned_count": orch_output.cleaned_count,
                "insight_count": len(orch_output.analyzer_output.insights) if orch_output.analyzer_output else 0,
                "report_id": report_id,
            })

        except Exception as e:
            logger.error(f"Workflow {state.workflow_id} failed: {e}", exc_info=True)
            state.status = "failed"
            state.error = str(e)
            await self._persist_stage_update(state)
            yield self._sse("error", {"error": str(e)[:500]})

    

    async def run_reentry_stream(self, original_workflow_id: str, target_stage: str, user_feedback: str, topic: str) -> AsyncGenerator[str, None]:
        original_state = await self.get_workflow(original_workflow_id)
        previous_output = original_state.stages if original_state else {}
        if original_state and original_state.result:
            previous_output = {**previous_output, "result": original_state.result}

        state = await self.create_workflow(topic=topic, max_items=5, dimensions=[])

        stage_idx_map = {s: i for i, s in enumerate(STAGE_SEQUENCE)}
        start_idx = stage_idx_map.get(target_stage, 0)
        visible_stages = STAGE_SEQUENCE[start_idx:]

        async for sse_event in self.run_workflow_stream(state, start_stage=target_stage, reentry_context=user_feedback):
            yield sse_event

    def _sse(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    async def get_history(self) -> list:
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(WorkflowRun).order_by(WorkflowRun.id.desc())
                )
                rows = result.scalars().all()
                return [
                    {
                        "workflow_id": r.workflow_id,
                        "topic": r.topic,
                        "status": r.status,
                        "current_stage": r.current_stage,
                        "stages": json.loads(r.stages_json) if r.stages_json else {},
                        "result": json.loads(r.result_json) if r.result_json else None,
                        "error": r.error,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning("Failed to load history from DB: %s", e)
            return [
                {
                    "workflow_id": wf.workflow_id,
                    "topic": wf.topic,
                    "status": wf.status,
                    "stages": {k: v for k, v in wf.stages.items()},
                    "result": wf.result,
                    "error": wf.error,
                }
                for wf in self._workflows.values()
            ]

workflow_service = WorkflowService()