"""
智能体工作流引擎

提供简化的市场洞察工作流执行。
状态流: idle → running(收集→清洗→分析→报告) → completed

Spec 1 (Phase 2 Human-in-the-Loop): 在数据采集阶段后插入"用户确认"环节。
- collecting 完成 → stage_state='awaiting_confirmation'，SSE 流正常结束
- 用户调用 /confirm: accept → 进入下一阶段；reject → 重跑当前阶段
- 完整的 SSE 重订阅机制：confirm 后启动新一轮 SSE 流

前端以对话形式展示，仅显示最终报告结果。
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, AsyncGenerator, List

import httpx
from fastapi import HTTPException
from sqlalchemy import select, update, and_
from app.core.config import settings
from app.core.db import async_session_factory
from app.core.runtime_config import rumtime_config
from app.models.workflow_run import WorkflowRun, StageState
from app.agents.orchestrator import OrchestratorAgent
from app.agents.master_agent import MasterAgent
from app.agents.collector import CollectorAgent
from app.agents.cleaner import CleanerAgent
from app.agents.analyzer import AnalyzerAgent
from app.agents.reporter import ReporterAgent
from app.schemas.agent import (
    OrchestratorInput, CollectorInput, CollectedItem,
    CleanerInput, AnalyzerInput, ReporterInput,
    DEFAULT_DIMENSIONS,
)
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
    def __init__(self, workflow_id: str, topic: str, max_items: int, dimensions: list, conversation_history: list = None, use_rag: bool = False, attachment_ids: Optional[list] = None):
        self.workflow_id = workflow_id
        self.topic = topic
        self.max_items = max_items
        self.dimensions = dimensions
        self.conversation_history = conversation_history or []
        self.attachment_ids: List[str] = attachment_ids or []
        self.current_stage = ""
        self.current_stage_index = -1
        self.status = "idle"
        self.error: Optional[str] = None
        self.stages: Dict[str, Any] = {}
        self.result: Optional[Dict[str, Any]] = None
        self.is_direct_response: bool = False
        self.use_rag: bool = use_rag
        # Phase 2 Human-in-the-Loop 状态机（Spec 1）
        self.stage_state: str = StageState.RUNNING
        self.stage_output: Optional[Dict[str, Any]] = None
        self.stage_history: List[Dict[str, Any]] = []
        # Pipeline confirm synchronization (asyncio.Event for internal wait)
        self._confirm_event = asyncio.Event()
        self._confirm_result: Dict[str, Any] = {}
        # Stop/cancel flag: set to True when user clicks stop button
        self.cancelled: bool = False

class WorkflowService:
    def __init__(self):
        self._workflows: Dict[str, WorkflowState] = {}
        # 保留对 IntentClassifier / DirectResponseService 的直接引用（向后兼容）
        self._intent_classifier = IntentClassifier()
        self._direct_response = DirectResponseService()
        # 主控 Agent（轻度重构：组合分类器 + 直答服务；OrchestratorAgent 按需实例化）
        # 旧的 _classify_intent() 仍可用，内部委托 IntentClassifier
        self.master_agent = MasterAgent(
            intent_classifier=self._intent_classifier,
            direct_response=self._direct_response,
        )

    async def _notify_report_completed(self, report_id: int, topic: str) -> None:
        """报告完成后异步触发通知。

        使用独立 session 避免依赖主工作流事务。任何异常均被捕获并记录日志，
        防止通知失败影响主流程。
        """
        try:
            from app.services.notification import NotificationService

            notif_svc = NotificationService()
            async with async_session_factory() as sess:
                # 读取报告以获取 title / summary
                from app.models.report import Report as ReportModel
                from sqlalchemy import select as sa_select
                result = await sess.execute(
                    sa_select(ReportModel).where(ReportModel.id == report_id)
                )
                report = result.scalar_one_or_none()
                if not report:
                    logger.warning("Notification skipped: report %s not found", report_id)
                    return

                title = f"【报告完成】{report.title or topic}"
                summary = report.summary or (report.content_markdown[:200] if report.content_markdown else "报告已生成，请前往查看。")
                content = f"<p>主题：{report.title or topic}</p><p>{summary}</p>"

                await notif_svc.notify(
                    session=sess,
                    trigger="report_ready",
                    title=title,
                    content=content,
                )
                logger.info("Notification sent for report %s", report_id)
        except Exception as e:
            logger.warning("Failed to send report completion notification (report_id=%s): %s", report_id, e)

    async def _classify_intent(self, message: str, conversation_history: list = None, has_existing_report: bool = False) -> dict:
        """向后兼容：直接委托 IntentClassifier.classify()
        等价于 master_agent.classify()"""
        return await self._intent_classifier.classify(message, conversation_history, has_existing_report)

    async def run_direct_response_stream(self, state: 'WorkflowState', use_rag: bool = None) -> AsyncGenerator[str, None]:
        """直答工作流 SSE 流。
        从 state 读取 topic / conversation_history / attachment_ids,
        use_rag 默认沿用 state.use_rag,允许调用方显式覆盖。
        """
        if use_rag is None:
            use_rag = getattr(state, "use_rag", False)
        async for chunk in self._direct_response.generate_response_stream(
            state.topic,
            conversation_history=state.conversation_history,
            use_rag=use_rag,
            attachment_ids=list(state.attachment_ids or []),
            workflow_state=state,
        ):
            yield chunk

    async def _run_and_persist_direct(
        self,
        state: 'WorkflowState',
        stream_iter: AsyncGenerator[str, None],
    ) -> AsyncGenerator[str, None]:
        """直答 SSE 流: 透传给上游,同时 parse SSE 提取 direct_response 的 content
        累积起来,流结束后写入 state.result["report_markdown"] 并持久化。

        修复:历史对话点开看不到 AI 回复的 bug。
        直答路径原本只持久化 status=completed,但 result 始终为 None,
        导致前端 loadHistoryFromServer 拉到历史后只显示用户消息,AI 回复完全丢失。
        """
        accumulated: list[str] = []
        # 每个 chunk 可能包含多个 SSE 事件,需逐 event 解析。
        # DirectResponseService._sse 输出格式:
        #   "event: <type>\ndata: <json>\n\n"
        # event 行的 type 才是关键字段(data 字段只含 content 等负载)
        current_event: Optional[str] = None
        async for chunk in stream_iter:
            if state.cancelled:
                return
            try:
                for line in chunk.split("\n"):
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: ") and current_event == "direct_response":
                        evt = json.loads(line[6:])
                        if isinstance(evt, dict):
                            c = evt.get("content", "")
                            if c:
                                accumulated.append(c)
                        current_event = None
            except Exception:
                # 解析失败不影响 yield,只是丢失部分累积内容
                pass
            yield chunk

        full_text = "".join(accumulated)
        if full_text:
            # 复用 result.report_markdown 字段,前端 loadHistoryFromServer
            # 已有的 `if (item.result && item.result.report_markdown)` 分支
            # 会自动把内容渲染为 assistant 消息。
            state.result = {
                "report_markdown": full_text,
                "chart_configs": [],
                "sections": [],
                "is_direct_response": True,
            }
            state.current_stage = "direct_response"
            state.status = "completed"
            await self._persist_stage_update(state)

    async def run_follow_up_stream(
        self,
        workflow_id: str,
        message: str,
        conversation_history: list,
        use_rag: bool = False,
    ) -> AsyncGenerator[str, None]:
        """对已有 workflow 发起追问：直接走直答 SSE 流，透传 use_rag。
        注:追问时用 message 覆盖 state.topic,attachment_ids 沿用 state 的(若前端在 follow-up 请求中
        显式传新附件,需在调用方负责更新 state.attachment_ids,这里只读)。
        """
        state = await self.get_workflow(workflow_id)
        if not state:
            yield self._sse("error", {"error": "Workflow not found"})
            return
        history = conversation_history if conversation_history is not None else state.conversation_history
        # 临时用追问消息覆盖 topic(避免污染持久化的 state.topic)
        original_topic = state.topic
        try:
            state.topic = message
            # 修复:用 _run_and_persist_direct 累积追问回复 content
            # 并写入 state.result,这样历史对话里也能看到追问的 AI 回复
            async for chunk in self._run_and_persist_direct(
                state,
                self.run_direct_response_stream(
                    state, use_rag=use_rag or state.use_rag
                ),
            ):
                yield chunk
        finally:
            state.topic = original_topic

    async def create_workflow(
        self,
        topic: str,
        max_items: int,
        dimensions: list = None,
        conversation_history: list = None,
        use_rag: bool = False,
        initial_stage: Optional[str] = None,
        attachment_ids: Optional[List[str]] = None,
        parent_workflow_id: Optional[str] = None,
    ) -> WorkflowState:
        """创建工作流。

        Args:
            initial_stage: 起始阶段。`orchestrate` 传 'collecting'、`reentry` 传 target_stage、
                `direct_response` 传 None。设置后 SSE 流端点 (stream-collecting/cleaning/...)
                才能通过 `state.current_stage == stage` 校验并开始流式推送。
            attachment_ids: 用户上传的附件 ID 列表,会在 collecting 阶段作为一手资料载入。
            parent_workflow_id: 历史追问聚合 spec: 追问时指向父工作流的 workflow_id,顶层对话为 None。
        """
        wf_id = str(uuid.uuid4())[:8]
        if dimensions is None:
            dimensions = []
        state = WorkflowState(
            wf_id,
            topic,
            max_items,
            dimensions,
            conversation_history,
            use_rag=use_rag,
            attachment_ids=attachment_ids,
        )
        if initial_stage:
            state.current_stage = initial_stage
            # 进入 running 状态机,准备流式执行
            state.status = "running"
        self._workflows[wf_id] = state

        try:
            async with async_session_factory() as session:
                wf_run = WorkflowRun(
                    workflow_id=wf_id,
                    topic=topic,
                    status=state.status,
                    current_stage=state.current_stage,
                    stages_json=json.dumps({}),
                    stage_state=StageState.RUNNING,  # Phase 2: 初始 running
                    stage_output=None,
                    stage_history=None,
                    parent_workflow_id=parent_workflow_id,
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
                    # Phase 2: 加载 state machine 字段
                    state.stage_state = wf_run.stage_state or StageState.RUNNING
                    state.stage_output = json.loads(wf_run.stage_output) if wf_run.stage_output else None
                    state.stage_history = json.loads(wf_run.stage_history) if wf_run.stage_history else []
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
                        # Phase 2: 同步 state machine
                        stage_state=state.stage_state,
                        stage_output=json.dumps(state.stage_output) if state.stage_output is not None else None,
                        stage_history=json.dumps(state.stage_history),
                    )
                )
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist stage update for %s: %s", state.workflow_id, e)

    async def run_workflow_stream(self, state: WorkflowState, start_stage: str = None, reentry_context: str = None, use_rag: bool = False) -> AsyncGenerator[str, None]:
        if state.is_direct_response:
            effective_use_rag = use_rag or state.use_rag
            state.status = "running"
            state.current_stage = "direct_response"
            await self._persist_stage_update(state)

            stream = self._direct_response.generate_response_stream(
                state.topic,
                conversation_history=state.conversation_history,
                workflow_id=state.workflow_id,
                use_rag=effective_use_rag,
                workflow_state=state,
            )
            # 修复:用 _run_and_persist_direct 累积 content 并写入 state.result,
            # 这样前端 loadHistoryFromServer 拉到历史后能看到 AI 回复
            async for chunk in self._run_and_persist_direct(state, stream):
                yield chunk
            return

        queue = asyncio.Queue()
        stage_idx_map = {s: i for i, s in enumerate(STAGE_SEQUENCE)}

        # 缓存每个阶段切换时由 OrchestratorAgent 传来的 stage_detail
        # key = 阶段名(当前要切到的状态,detail 属于"上一阶段")
        # value = {"summary": ..., "detail": ...}
        pending_stage_details: dict = {}

        async def sse_callback(task_id, status, error, stage_detail=None):
            await queue.put((status, error, stage_detail))

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
                if state.cancelled:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
                    return
                try:
                    status, error, stage_detail = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                # 缓存新阶段对应的 detail(它是"上一阶段"的产出,在 stage_complete 时用)
                if stage_detail and status in STAGE_SEQUENCE:
                    pending_stage_details[status] = stage_detail

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
                        # 关键修复:把上一阶段的 detail 填到 stage_complete 事件中
                        prev_detail = pending_stage_details.get(prev_stage)
                        stage_complete_payload = {
                            "stage": prev_stage, "label": STAGE_LABELS[prev_stage],
                        }
                        if prev_detail:
                            stage_complete_payload["summary"] = prev_detail.get("summary", {})
                            stage_complete_payload["detail"] = prev_detail.get("detail", {})
                            # 同步持久化到 state.stages,供历史对话重新加载时使用
                            state.stages = state.stages or {}
                            state.stages[prev_stage] = prev_detail
                        yield self._sse("stage_complete", stage_complete_payload)
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
                # 收尾:把最后阶段的 detail 也填到 stage_complete 事件
                last_detail = pending_stage_details.get(prev_stage)
                final_payload = {
                    "stage": prev_stage, "label": STAGE_LABELS.get(prev_stage, prev_stage),
                }
                if last_detail:
                    final_payload["summary"] = last_detail.get("summary", {})
                    final_payload["detail"] = last_detail.get("detail", {})
                    # 同步持久化最后阶段的 detail,确保历史加载可见
                    state.stages = state.stages or {}
                    state.stages[prev_stage] = last_detail
                yield self._sse("stage_complete", final_payload)

            state.status = "completed"
            reporter = orch_output.reporter_output
            state.result = {
                "report_markdown": reporter.markdown_report if reporter else "",
                "chart_configs": reporter.chart_configs if reporter else [],
                "chart_images": reporter.chart_images if reporter else [],
                "dimension_illustrations": reporter.dimension_illustrations if reporter else [],
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
                        chart_images = report_data.get("chart_images", [])
                        dimension_illustrations = report_data.get("dimension_illustrations", [])
                        logger.info(
                            "[DEBUG][workflow] run_workflow_stream saving report task=%s "
                            "chart_images=%d, dimension_illustrations=%d",
                            state.workflow_id, len(chart_images), len(dimension_illustrations),
                        )
                        report = await report_svc.create_from_workflow(
                            sess,
                            task_id=state.workflow_id,
                            title=state.topic,
                            content_markdown=report_data.get("report_markdown", ""),
                            summary=report_data.get("report_markdown", "")[:200] if report_data.get("report_markdown") else None,
                            chart_images=chart_images,
                            dimension_illustrations=dimension_illustrations,
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

    async def run_pipeline_stream(self, state: WorkflowState, use_rag: bool = False) -> AsyncGenerator[str, None]:
        """统一 pipeline: 自动串联四阶段（collecting → cleaning → analyzing → reporting）。

        行为：
        - 直答路径：调 DirectResponseService 流式输出
        - 四阶段路径：连续执行到底，不再插入人工审阅环节
        - 阶段间通过 state.stages[stage]["_raw"] 传递数据
        - 任一阶段失败即中止并 emit stage_error
        """
        # 直答路径
        if state.is_direct_response:
            state.status = "running"
            await self._persist_stage_update(state)
            stream = self._direct_response.generate_response_stream(
                state.topic,
                conversation_history=state.conversation_history,
                workflow_id=state.workflow_id,
                use_rag=use_rag or state.use_rag,
                # 必须显式把 state.attachment_ids 传给 generate_response_stream,
                # 否则多模态 LLM 收不到图片,只能回"我无法查看图片"
                attachment_ids=list(state.attachment_ids or []),
                workflow_state=state,
            )
            # 累积 content 并写入 state.result,这样历史对话里也能看到 AI 回复
            async for chunk in self._run_and_persist_direct(state, stream):
                if state.cancelled:
                    return
                yield chunk
            return

        stages = ["collecting", "cleaning", "analyzing", "reporting"]
        state.status = "running"
        state.current_stage = stages[0]
        state.stage_state = StageState.RUNNING
        await self._persist_stage_update(state)

        for idx, stage in enumerate(stages):
            if state.cancelled:
                return

            state.current_stage = stage
            state.stage_state = StageState.RUNNING
            stage_start_time = time.time()

            # SSE: stage_start
            yield self._sse("stage_start", {
                "stage": stage,
                "label": STAGE_LABELS[stage],
                "icon": STAGE_ICONS[stage],
                "index": idx,
                "total": len(stages),
            })

            try:
                # 跑当前阶段
                stage_output, raw_output = await self._run_single_stage(state, stage)

                # 写 stages 摘要
                existing = state.stages.get(stage, {}) if state.stages else {}
                state.stages[stage] = {**existing, "_raw": raw_output}
                if stage == "collecting":
                    state.stages[stage]["item_count"] = raw_output.get("item_count", 0)
                elif stage == "cleaning":
                    state.stages[stage]["total_in"] = raw_output.get("stats", {}).get("total_in", 0)
                    state.stages[stage]["total_out"] = raw_output.get("stats", {}).get("total_out", 0)

                # SSE: stage_complete
                if stage == "collecting":
                    collecting_raw = raw_output
                    keywords = collecting_raw.get("metadata", {}).get("keywords_used", [])
                    total_search = collecting_raw.get("metadata", {}).get("total_search_results", 0)
                    items = collecting_raw.get("items", [])
                    yield self._sse("stage_complete", {
                        "stage": stage,
                        "label": STAGE_LABELS[stage],
                        "summary": {
                            "keywords_count": len(keywords),
                            "total_search_results": total_search,
                            "item_count": len(items),
                            "duration_seconds": round(time.time() - stage_start_time, 1),
                        },
                        "detail": {
                            "keywords": keywords,
                            "total_search_results": total_search,
                            "items": [
                                {"title": it.get("title", ""), "snippet": (it.get("content", "") or "")[:200], "source_uri": it.get("source_uri", "")}
                                for it in items
                            ],
                        },
                    })
                elif stage == "cleaning":
                    cleaning_raw = raw_output
                    stats = cleaning_raw.get("stats", {})
                    ops = cleaning_raw.get("cleaning_operations", {})
                    cleaning_summary = f"共处理 {stats.get('total_in', 0)} 条数据，清洗后保留 {stats.get('total_out', 0)} 条。"
                    if ops.get("duplicates_removed"):
                        cleaning_summary += f"移除重复数据 {ops['duplicates_removed']} 条，"
                    if ops.get("low_quality_filtered"):
                        cleaning_summary += f"过滤低质量内容 {ops['low_quality_filtered']} 条，"
                    if ops.get("format_standardized"):
                        cleaning_summary += f"标准化格式 {ops['format_standardized']} 条。"
                    yield self._sse("stage_complete", {
                        "stage": stage,
                        "label": STAGE_LABELS[stage],
                        "summary": {
                            "total_in": stats.get("total_in", 0),
                            "total_out": stats.get("total_out", 0),
                            "removed_count": stats.get("removed_count", 0),
                            "duration_seconds": round(time.time() - stage_start_time, 1),
                            "duplicates_removed": ops.get("duplicates_removed", 0),
                            "low_quality_filtered": ops.get("low_quality_filtered", 0),
                            "format_standardized": ops.get("format_standardized", 0),
                        },
                        "detail": {
                            "stats": stats,
                            "cleaning_operations": ops,
                            "cleaning_summary": cleaning_summary,
                        },
                    })
                elif stage == "analyzing":
                    analyzing_raw = raw_output
                    insights = analyzing_raw.get("insights", [])
                    dimensions = list(set(ins.get("dimension", "") for ins in insights if ins.get("dimension")))
                    rag_results_count = analyzing_raw.get("rag_results_count", 0)
                    rag_results = analyzing_raw.get("rag_results", [])
                    yield self._sse("stage_complete", {
                        "stage": stage,
                        "label": STAGE_LABELS[stage],
                        "summary": {
                            "insight_count": len(insights),
                            "dimensions": dimensions,
                            "duration_seconds": round(time.time() - stage_start_time, 1),
                            "rag_results_count": rag_results_count,
                        },
                        "detail": {
                            "insights": insights,
                            "dimensions": dimensions,
                            "rag_results_count": rag_results_count,
                            "rag_results": rag_results,
                        },
                    })
                elif stage == "reporting":
                    reporting_raw = raw_output
                    report_text = reporting_raw.get("report", "")
                    chart_configs = reporting_raw.get("chart_configs", [])
                    chart_images = reporting_raw.get("chart_images", [])
                    dimension_illustrations = reporting_raw.get("dimension_illustrations", [])
                    yield self._sse("stage_complete", {
                        "stage": stage,
                        "label": STAGE_LABELS[stage],
                        "summary": {
                            "report_length": len(report_text),
                            "chart_count": len(chart_configs),
                            "duration_seconds": round(time.time() - stage_start_time, 1),
                        },
                        "detail": {
                            "report_markdown": report_text,
                            "chart_count": len(chart_configs),
                            "chart_images": chart_images,
                            "dimension_illustrations": dimension_illustrations,
                        },
                    })
                else:
                    yield self._sse("stage_complete", {
                        "stage": stage,
                        "label": STAGE_LABELS[stage],
                    })
            except Exception as e:
                logger.error(f"[{state.workflow_id}] {stage} failed: {e}", exc_info=True)
                state.status = "failed"
                state.error = str(e)[:500]
                await self._persist_stage_update(state)
                yield self._sse("stage_error", {
                    "stage": stage,
                    "label": STAGE_LABELS[stage],
                    "error": state.error,
                })
                return

        # All stages done
        state.status = "completed"
        state.stage_state = StageState.COMPLETED
        # Build result from reporting stage
        reporting_raw = (state.stages.get("reporting", {}) or {}).get("_raw", {})
        state.result = {
            "report_markdown": reporting_raw.get("report", ""),
            "chart_configs": reporting_raw.get("chart_configs", []),
            "chart_images": reporting_raw.get("chart_images", []),
            "sections": reporting_raw.get("sections", []),
            "dimension_illustrations": reporting_raw.get("dimension_illustrations", []),
        }
        await self._persist_stage_update(state)

        # Auto-save report
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
                    chart_images = state.result.get("chart_images", [])
                    dimension_illustrations = state.result.get("dimension_illustrations", [])
                    logger.info(
                        "[DEBUG][workflow] run_pipeline_stream saving report task=%s "
                        "chart_images=%d, dimension_illustrations=%d",
                        state.workflow_id, len(chart_images), len(dimension_illustrations),
                    )
                    report = await report_svc.create_from_workflow(
                        sess, task_id=state.workflow_id, title=state.topic,
                        content_markdown=state.result.get("report_markdown", ""),
                        summary=(state.result.get("report_markdown", "")[:200] if state.result.get("report_markdown") else None),
                        chart_images=chart_images,
                        dimension_illustrations=dimension_illustrations,
                    )
                    report_id = report.id
        except Exception as e:
            logger.warning("Failed to auto-save report: %s", e)

        yield self._sse("completed", {
            "workflow_id": state.workflow_id,
            "topic": state.topic,
            "report_markdown": state.result.get("report_markdown", ""),
            "chart_configs": state.result.get("chart_configs", []),
            "sections": state.result.get("sections", []),
            "report_id": report_id,
        })

    async def run_reentry_stream(self, original_workflow_id: str, target_stage: str, user_feedback: str, topic: str) -> AsyncGenerator[str, None]:
        original_state = await self.get_workflow(original_workflow_id)
        previous_output = original_state.stages if original_state else {}
        if original_state and original_state.result:
            previous_output = {**previous_output, "result": original_state.result}

        state = await self.create_workflow(
            topic=topic,
            max_items=5,
            dimensions=original_state.dimensions if original_state else [],
        )

        stage_idx_map = {s: i for i, s in enumerate(STAGE_SEQUENCE)}
        start_idx = stage_idx_map.get(target_stage, 0)
        visible_stages = STAGE_SEQUENCE[start_idx:]

        async for sse_event in self.run_workflow_stream(state, start_stage=target_stage, reentry_context=user_feedback):
            yield sse_event

    # ========== Stage runner (四阶段连续执行,无人工审阅) ==========

    async def _run_single_stage(self, state: WorkflowState, stage: str) -> tuple:
        """Spec 2: 跑单个 stage，返回 (stage_output_preview, raw_output_dict)。

        raw_output_dict 是给下一阶段消费的完整 agent 输出（dict 化）。
        stage_output_preview 是给前端展示的精简版。
        """
        if stage == "collecting":
            return await self._run_collecting_stage(state)
        elif stage == "cleaning":
            return await self._run_cleaning_stage(state)
        elif stage == "analyzing":
            return await self._run_analyzing_stage(state)
        elif stage == "reporting":
            return await self._run_reporting_stage(state)
        else:
            raise ValueError(f"Unknown stage: {stage}")

    async def _run_collecting_stage(self, state: WorkflowState):
        """收集阶段: 调 CollectorAgent，序列化 sources 列表。"""
        collector = CollectorAgent()
        col_in = CollectorInput(
            task_id=state.workflow_id,
            topic=state.topic,
            max_items=state.max_items,
            attachment_ids=list(state.attachment_ids or []),
        )
        col_out = await collector.execute(col_in)
        if not col_out.success:
            raise RuntimeError(f"Collector failed: {col_out.error}")

        sources = [
            {
                "source_type": it.source_type,
                "source_uri": it.source_uri,
                "title": it.title,
                "snippet": (it.content or "")[:300],
                "content_length": len(it.content or ""),
                "metadata": it.metadata or {},
            }
            for it in col_out.items
        ]
        user_attachment_count = int((col_out.metadata or {}).get("user_attachment_count", 0))
        stage_output = {
            "stage": "collecting",
            "sources": sources,
            "item_count": len(sources),
            "warning": col_out.warning,
            "user_attachment_count": user_attachment_count,
        }
        raw_output = {
            "items": [it.model_dump() for it in col_out.items],
            "item_count": len(sources),
            "warning": col_out.warning,
            "metadata": col_out.metadata or {},
        }
        return stage_output, raw_output

    async def _run_cleaning_stage(self, state: WorkflowState):
        """清洗阶段: 用 collecting 阶段的 raw items 调 CleanerAgent。

        需要的输入来自 state.stages["collecting"]["_raw"]["items"]。
        """
        collecting_raw = (state.stages.get("collecting", {}) or {}).get("_raw", {})
        items_dict = collecting_raw.get("items", [])
        if not items_dict:
            raise RuntimeError("Cannot run cleaning: no items from collecting stage")

        # 重建 Pydantic 模型
        raw_items = [CollectedItem(**it) for it in items_dict]

        cleaner = CleanerAgent()
        cln_in = CleanerInput(task_id=state.workflow_id, raw_items=raw_items)
        cln_out = await cleaner.execute(cln_in)
        if not cln_out.success:
            raise RuntimeError(f"Cleaner failed: {cln_out.error}")

        cleaned_items_dict = [it.model_dump() for it in cln_out.cleaned_items]
        cleaning_operations = cln_out.cleaning_operations or {
            "duplicates_removed": 0,
            "low_quality_filtered": 0,
            "format_standardized": 0,
        }
        stage_output = {
            "stage": "cleaning",
            "cleaned_items": cleaned_items_dict,
            "stats": {
                "total_in": len(raw_items),
                "total_out": len(cln_out.cleaned_items),
                "removed_count": cln_out.total_removed,
            },
            "cleaning_operations": cleaning_operations,
        }
        raw_output = {
            "cleaned_items": cleaned_items_dict,
            "stats": stage_output["stats"],
            "cleaning_operations": cleaning_operations,
        }
        return stage_output, raw_output

    async def _run_analyzing_stage(self, state: WorkflowState):
        """分析阶段: 用 cleaning 阶段的 cleaned_items 调 AnalyzerAgent。"""
        from app.schemas.agent import CleanedItem as CleanedItemModel

        cleaning_raw = (state.stages.get("cleaning", {}) or {}).get("_raw", {})
        cleaned_items_dict = cleaning_raw.get("cleaned_items", [])
        if not cleaned_items_dict:
            raise RuntimeError("Cannot run analyzing: no cleaned_items from cleaning stage")

        cleaned_items = [CleanedItemModel(**it) for it in cleaned_items_dict]

        analyzer = AnalyzerAgent()
        ana_in = AnalyzerInput(
            task_id=state.workflow_id,
            topic=state.topic,
            cleaned_items=cleaned_items,
            dimensions=state.dimensions or list(DEFAULT_DIMENSIONS),
        )
        ana_out = await analyzer.execute(ana_in)
        if not ana_out.success:
            raise RuntimeError(f"Analyzer failed: {ana_out.error}")

        insights_dict = [it.model_dump() for it in ana_out.insights]
        stage_output = {
            "stage": "analyzing",
            "insights": insights_dict,
            "dimensions": state.dimensions or [],
            "summary": ana_out.summary,
        }
        raw_output = {
            "analyzer_output": ana_out.model_dump(),
            "insights": insights_dict,
        }
        return stage_output, raw_output

    async def _run_reporting_stage(self, state: WorkflowState):
        """报告阶段: 用 analyzing 阶段的 analyzer_output 调 ReporterAgent。"""
        from app.schemas.agent import AnalyzerOutput as AnalyzerOutputModel

        analyzing_raw = (state.stages.get("analyzing", {}) or {}).get("_raw", {})
        analyzer_output_dict = analyzing_raw.get("analyzer_output", {})
        if not analyzer_output_dict:
            raise RuntimeError("Cannot run reporting: no analyzer_output from analyzing stage")

        analyzer_output = AnalyzerOutputModel(**analyzer_output_dict)

        # 构造 source_contents（reporter 需要 cleaned items 的纯文本）
        cleaning_raw = (state.stages.get("cleaning", {}) or {}).get("_raw", {})
        cleaned_items_dict = cleaning_raw.get("cleaned_items", [])
        source_contents = []
        for ci in cleaned_items_dict:
            chunks = ci.get("content_chunks") or []
            full_text = "\n".join(chunks) if chunks else ci.get("summary", "")
            source_contents.append({
                "uri": ci.get("source_uri", ""),
                "title": ci.get("title", ""),
                "content": full_text[:1000],
            })

        reporter = ReporterAgent()
        rep_in = ReporterInput(
            task_id=state.workflow_id,
            topic=state.topic,
            analyzer_output=analyzer_output,
            include_charts=True,
            dimensions=state.dimensions or [],
            source_contents=source_contents,
        )
        rep_out = await reporter.execute(rep_in)
        if not rep_out.success:
            raise RuntimeError(f"Reporter failed: {rep_out.error}")

        sections_dict = [s.model_dump() for s in rep_out.sections]
        # 调试日志:记录图片数量便于排查持久化问题
        chart_images_count = len(rep_out.chart_images or [])
        dim_illus_count = len(rep_out.dimension_illustrations or [])
        logger.info(
            "[DEBUG][workflow] _run_reporting_stage task=%s "
            "chart_images=%d (total_b64_size=%d), "
            "dimension_illustrations=%d (total_b64_size=%d)",
            state.workflow_id,
            chart_images_count,
            sum(len(ci.get("base64", "")) for ci in (rep_out.chart_images or [])),
            dim_illus_count,
            sum(len(ci.get("base64", "")) for ci in (rep_out.dimension_illustrations or [])),
        )
        # 校验 base64 字符串可被 JSON 序列化(避免 Pydantic 报错或数据库写入失败)
        try:
            json.dumps({
                "chart_images": rep_out.chart_images,
                "dimension_illustrations": rep_out.dimension_illustrations,
            }, default=str)
        except TypeError as je:
            logger.error(
                "[DEBUG][workflow] ReporterOutput images NOT JSON serializable: %s", je
            )
            raise

        stage_output = {
            "stage": "reporting",
            "report": rep_out.markdown_report,
            "sections": sections_dict,
        }
        raw_output = {
            "report": rep_out.markdown_report,
            "sections": sections_dict,
            "chart_configs": rep_out.chart_configs,
            "chart_images": rep_out.chart_images,
            "dimension_illustrations": rep_out.dimension_illustrations,
        }
        return stage_output, raw_output

    async def _call_llm(self, prompt: str, timeout: int = 60) -> str:
        """Call the LLM with the given prompt and return the text response."""
        llm_provider = rumtime_config.get("llm_provider")
        default_model = rumtime_config.get("default_model")
        llm_base_url = rumtime_config.get("llm_base_url")
        llm_api_key = settings.llm_api_key

        # Try DB config override
        try:
            db_config = await rumtime_config.get_default_model_config("llm")
            if db_config:
                llm_provider = db_config["provider"].lower() if db_config.get("provider") else llm_provider
                default_model = db_config.get("model_name") or default_model
                if db_config.get("base_url"):
                    llm_base_url = db_config["base_url"]
                if db_config.get("api_key"):
                    llm_api_key = db_config["api_key"]
        except Exception:
            pass

        if llm_provider == "gpustack":
            llm_url = f"{llm_base_url.rstrip('/')}/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {llm_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": default_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": rumtime_config.get("temperature"),
                "max_tokens": rumtime_config.get("max_tokens"),
            }
        else:
            llm_url = f"{llm_base_url.rstrip('/')}/api/generate"
            headers = {}
            payload = {
                "model": default_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": rumtime_config.get("temperature")},
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(llm_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            if llm_provider == "gpustack":
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                return data.get("response", "")

    def _sse(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    async def cleanup_orphan_workflows(self):
        """清理长时间停留在 running 状态的孤立工作流记录。

        查找 status='running' 且 updated_at 超过 10 分钟前的记录，
        将其标记为 'failed' 并从内存中移除。
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
            async with async_session_factory() as session:
                result = await session.execute(
                    select(WorkflowRun).where(
                        and_(
                            WorkflowRun.status == "running",
                            WorkflowRun.updated_at <= cutoff,
                        )
                    )
                )
                orphans = result.scalars().all()
                count = len(orphans)
                if count > 0:
                    for orphan in orphans:
                        orphan.status = "failed"
                        # 清理内存中对应的 state
                        self._workflows.pop(orphan.workflow_id, None)
                    await session.commit()
                    logger.info("Cleaned up %d orphan workflow(s)", count)
        except Exception as e:
            logger.warning("Failed to cleanup orphan workflows: %s", e)

    async def get_history(self) -> list:
        """返回分组后的历史列表(历史追问聚合 spec):
        - 顶层 workflow: parent_workflow_id IS NULL 或其父工作流已不存在(孤儿)
        - 每个顶层 dict 内嵌 children 列表(其追问工作流,按 created_at 正序)
        """
        def _serialize(r) -> dict:
            return {
                "workflow_id": r.workflow_id,
                "topic": r.topic,
                "status": r.status,
                "current_stage": r.current_stage,
                "stages": json.loads(r.stages_json) if r.stages_json else {},
                "result": json.loads(r.result_json) if r.result_json else None,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "parent_workflow_id": r.parent_workflow_id,
            }

        try:
            async with async_session_factory() as session:
                # 按 created_at 正序取,方便 children 排序时无需再排序
                result = await session.execute(
                    select(WorkflowRun).order_by(WorkflowRun.created_at.asc())
                )
                rows = list(result.scalars().all())

                # 构造 id 集合 + 父 → 子 索引
                id_set = {r.workflow_id for r in rows}
                children_by_parent: dict[str, list] = {}
                top_level_rows: list = []
                for r in rows:
                    if r.parent_workflow_id and r.parent_workflow_id in id_set:
                        children_by_parent.setdefault(r.parent_workflow_id, []).append(r)
                    else:
                        # parent 为空 或 父已不存在 → 顶层(含孤儿追问)
                        top_level_rows.append(r)

                grouped: list[dict] = []
                for r in top_level_rows:
                    item = _serialize(r)
                    item.pop("parent_workflow_id", None)  # 顶层不需要暴露
                    item["children"] = [
                        _serialize(c)
                        for c in children_by_parent.get(r.workflow_id, [])
                    ]
                    grouped.append(item)

                # 顶层之间按时间倒序展示(最新在前)
                grouped.sort(key=lambda x: x.get("created_at") or "", reverse=True)
                return grouped
        except Exception as e:
            logger.warning("Failed to load history from DB: %s", e)
            # 内存回退路径(无 DB 时):全部按顶层处理
            return [
                {
                    "workflow_id": wf.workflow_id,
                    "topic": wf.topic,
                    "status": wf.status,
                    "stages": {k: v for k, v in wf.stages.items()},
                    "result": wf.result,
                    "error": wf.error,
                    "created_at": None,
                    "children": [],
                }
                for wf in self._workflows.values()
            ]

    async def delete_workflow(self, workflow_id: str) -> bool:
        """从内存和 DB 中删除工作流记录。

        返回:
            True  - 内存或 DB 中有记录被删除
            False - 工作流不存在
        """
        deleted = False
        # 1. 清理内存状态(若存在)
        if workflow_id in self._workflows:
            self._workflows.pop(workflow_id, None)
            deleted = True

        # 2. 清理 DB 记录
        try:
            async with async_session_factory() as session:
                row = await session.execute(
                    select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)
                )
                wf = row.scalar_one_or_none()
                if wf is not None:
                    await session.delete(wf)
                    await session.commit()
                    deleted = True
        except Exception as e:
            logger.warning("Failed to delete workflow from DB: %s", e)

        return deleted

    async def stop_workflow(self, workflow_id: str) -> bool:
        """停止正在运行的工作流。

        设置 cancelled 标志，让正在执行的 SSE 流尽快退出。
        返回 True 表示找到了工作流并标记了停止。
        """
        state = await self.get_workflow(workflow_id)
        if not state:
            return False
        state.cancelled = True
        state.status = "failed"
        state.error = "用户手动停止"
        # 如果 pipeline 正在等待事件，唤醒它让它退出
        if state._confirm_event is not None:
            state._confirm_result = {"decision": "skip"}
            state._confirm_event.set()
        await self._persist_stage_update(state)
        logger.info("Workflow %s stopped by user", workflow_id)
        return True

workflow_service = WorkflowService()