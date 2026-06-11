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
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, AsyncGenerator, List

from fastapi import HTTPException
from sqlalchemy import select, update
from app.core.db import async_session_factory
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

# 最大重试次数（防止用户无限重试耗尽搜索 API 配额）
MAX_RETRY_PER_STAGE = 3  # Spec 2: 从 5 改为 3


class WorkflowState:
    def __init__(self, workflow_id: str, topic: str, max_items: int, dimensions: list, conversation_history: list = None, use_rag: bool = False):
        self.workflow_id = workflow_id
        self.topic = topic
        self.max_items = max_items
        self.dimensions = dimensions
        self.conversation_history = conversation_history or []
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

    async def _classify_intent(self, message: str, conversation_history: list = None, has_existing_report: bool = False) -> dict:
        """向后兼容：直接委托 IntentClassifier.classify()
        等价于 master_agent.classify()"""
        return await self._intent_classifier.classify(message, conversation_history, has_existing_report)

    async def run_direct_response_stream(self, message: str, conversation_history: list = None, use_rag: bool = False) -> AsyncGenerator[str, None]:
        async for chunk in self._direct_response.generate_response_stream(
            message, conversation_history, use_rag=use_rag
        ):
            yield chunk

    async def run_follow_up_stream(
        self,
        workflow_id: str,
        message: str,
        conversation_history: list,
        use_rag: bool = False,
    ) -> AsyncGenerator[str, None]:
        """对已有 workflow 发起追问：直接走直答 SSE 流，透传 use_rag。"""
        state = await self.get_workflow(workflow_id)
        if not state:
            yield self._sse("error", {"error": "Workflow not found"})
            return
        history = conversation_history if conversation_history is not None else state.conversation_history
        async for chunk in self.run_direct_response_stream(
            message, history, use_rag=use_rag or state.use_rag
        ):
            yield chunk

    async def create_workflow(self, topic: str, max_items: int, dimensions: list = None, conversation_history: list = None, use_rag: bool = False) -> WorkflowState:
        wf_id = str(uuid.uuid4())[:8]
        if dimensions is None:
            dimensions = []
        state = WorkflowState(wf_id, topic, max_items, dimensions, conversation_history, use_rag=use_rag)
        self._workflows[wf_id] = state

        try:
            async with async_session_factory() as session:
                wf_run = WorkflowRun(
                    workflow_id=wf_id,
                    topic=topic,
                    status="idle",
                    current_stage="",
                    stages_json=json.dumps({}),
                    stage_state=StageState.RUNNING,  # Phase 2: 初始 running
                    stage_output=None,
                    stage_history=None,
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

            async for chunk in self._direct_response.generate_response_stream(
                state.topic,
                conversation_history=state.conversation_history,
                workflow_id=state.workflow_id,
                use_rag=effective_use_rag,
            ):
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

    # ========== Phase 2 Human-in-the-Loop (Spec 1 + Spec 2) ==========

    async def run_collecting_only_stream(self, state: WorkflowState) -> AsyncGenerator[str, None]:
        """Spec 1: 仅运行 collecting 阶段（保留作向后兼容的薄包装）。

        Spec 2 改造后，内部委托 run_stage_only_stream(state, "collecting")。
        SSE 事件格式与之前完全一致，老客户端零影响。
        """
        async for sse_event in self.run_stage_only_stream(state, "collecting"):
            yield sse_event

    async def run_stage_only_stream(self, state: WorkflowState, stage: str) -> AsyncGenerator[str, None]:
        """Spec 2: 通用 stage runner。跑指定 stage，结束后进入 awaiting_confirmation 状态。

        dispatch 表:
        - collecting → CollectorAgent
        - cleaning   → CleanerAgent
        - analyzing  → AnalyzerAgent
        - reporting  → ReporterAgent

        每个 stage 完成后写:
        - state.stage_output: 给前端展示用的精简版（preview）
        - state.stages[stage]["_raw"]: 给下一阶段消费用的完整 agent 输出（dict 化）
        """
        if stage not in STAGE_SEQUENCE:
            raise ValueError(f"Unknown stage: {stage}")

        logger.info(f"[{state.workflow_id}] run_stage_only_stream: stage='{stage}', topic='{state.topic}'")

        # 状态校验
        if state.stage_state != StageState.RUNNING:
            raise RuntimeError(
                f"Workflow {state.workflow_id} is not in 'running' state "
                f"(current: {state.stage_state}). Cannot run stage."
            )
        if state.current_stage != stage:
            raise RuntimeError(
                f"Workflow {state.workflow_id} current_stage is '{state.current_stage}', "
                f"but requested to run '{stage}'"
            )

        state.status = "running"
        await self._persist_stage_update(state)

        stage_idx = STAGE_SEQUENCE.index(stage)

        # SSE: stage_start
        yield self._sse("stage_start", {
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "icon": STAGE_ICONS[stage],
            "index": stage_idx,
            "total": len(STAGE_SEQUENCE),
        })

        try:
            # Dispatch
            stage_output, raw_output = await self._run_single_stage(state, stage)

            # 写 state
            state.stage_output = stage_output
            # 保留原有 stages 摘要（向后兼容） + 加 _raw 给下一阶段
            existing = state.stages.get(stage, {}) if state.stages else {}
            state.stages[stage] = {**existing, "_raw": raw_output}
            # 同步 stage_output 里的关键 stats（便于其他模块读）
            if stage == "collecting":
                state.stages[stage]["item_count"] = raw_output.get("item_count", 0)
                state.stages[stage]["warning"] = raw_output.get("warning", "")
            elif stage == "cleaning":
                state.stages[stage]["total_in"] = raw_output.get("stats", {}).get("total_in", 0)
                state.stages[stage]["total_out"] = raw_output.get("stats", {}).get("total_out", 0)

            state.stage_state = StageState.AWAITING_CONFIRMATION
            await self._persist_stage_update(state)

            # SSE: stage_complete
            yield self._sse("stage_complete", {
                "stage": stage,
                "label": STAGE_LABELS[stage],
                "stage_state": StageState.AWAITING_CONFIRMATION,
                "stage_output": stage_output,
            })
            logger.info(
                f"[{state.workflow_id}] {stage} stage done, awaiting confirmation"
            )
        except Exception as e:
            logger.error(f"[{state.workflow_id}] {stage} stage failed: {e}", exc_info=True)
            state.status = "failed"
            state.error = str(e)[:500]
            state.stage_state = StageState.FAILED
            await self._persist_stage_update(state)
            yield self._sse("stage_error", {
                "stage": stage,
                "label": STAGE_LABELS[stage],
                "error": state.error,
            })

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
        stage_output = {
            "stage": "collecting",
            "sources": sources,
            "item_count": len(sources),
            "warning": col_out.warning,
        }
        raw_output = {
            "items": [it.model_dump() for it in col_out.items],
            "item_count": len(sources),
            "warning": col_out.warning,
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
        stage_output = {
            "stage": "cleaning",
            "cleaned_items": cleaned_items_dict,
            "stats": {
                "total_in": len(raw_items),
                "total_out": len(cln_out.cleaned_items),
                "removed_count": cln_out.total_removed,
            },
        }
        raw_output = {
            "cleaned_items": cleaned_items_dict,
            "stats": stage_output["stats"],
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
            dimensions=state.dimensions or [
                "宏观经济环境", "行业形势与趋势", "细分板块分析", "竞争格局与对手",
            ],
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
        }
        return stage_output, raw_output

    async def confirm_stage(self, state: WorkflowState, decision: str,
                            user_edits: Optional[dict] = None,
                            user_feedback: Optional[str] = None) -> Dict[str, Any]:
        """Spec 1+2: 处理用户阶段确认。

        状态机：
        - 当前 stage_state 必须 == 'awaiting_confirmation'，否则 409
        - decision='accept': stage_state='running'，进入下一阶段
        - decision='reject': stage_state='running'，重跑当前阶段（带 user_edits 合并）
        - decision='skip': 等价 accept，但 user_edits/user_feedback 都忽略（不看预览直接过）
        - 重试次数 = len(stage_history) 中 reject 计数 > MAX_RETRY_PER_STAGE → 429
          （accept 和 skip 不计入重试）
        """
        if state.stage_state != StageState.AWAITING_CONFIRMATION:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot confirm: current stage_state is '{state.stage_state}', "
                       f"expected '{StageState.AWAITING_CONFIRMATION}'",
            )

        if decision not in ("accept", "reject", "skip"):
            raise HTTPException(status_code=422, detail=f"Invalid decision: {decision}")

        # 重试次数检查（仅 reject 受限，且只数 reject 决策）
        reject_count = sum(1 for h in state.stage_history if h.get("decision") == "reject")
        if decision == "reject" and reject_count >= MAX_RETRY_PER_STAGE:
            raise HTTPException(
                status_code=429,
                detail=f"重试次数过多（已 {len(state.stage_history)} 次），请接受或取消工作流",
            )

        # 记录到 stage_history
        history_entry = {
            "stage": state.current_stage,
            "decision": decision,
            "user_edits": user_edits,
            "user_feedback": user_feedback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        state.stage_history.append(history_entry)

        # 决定下一阶段
        if decision in ("accept", "skip"):
            # accept 和 skip 行为一致：进入下一阶段
            # 区别仅在 history 记录（skip 不带 user_edits）
            current_idx = STAGE_SEQUENCE.index(state.current_stage) if state.current_stage in STAGE_SEQUENCE else -1
            if current_idx < 0 or current_idx >= len(STAGE_SEQUENCE) - 1:
                # 已经在 reporting 阶段（理论上不应该，但兜底）
                next_stage = None
                state.stage_state = StageState.COMPLETED
            else:
                next_stage = STAGE_SEQUENCE[current_idx + 1]
                state.current_stage = next_stage
                state.stage_state = StageState.RUNNING
            state.stage_output = None  # 清除上一次的输出
        else:
            # reject: 重跑当前阶段
            state.stage_state = StageState.RUNNING
            # 应用 user_edits 合并到 topic
            if user_edits:
                extra_urls = user_edits.get("extra_urls") or []
                extra_keywords = user_edits.get("extra_keywords") or []
                if extra_urls:
                    state.topic = f"{state.topic}\n\n补充URL:\n" + "\n".join(extra_urls)
                if extra_keywords:
                    state.topic = f"{state.topic}\n\n补充关键词: " + ", ".join(extra_keywords)
            if user_feedback:
                state.topic = f"{state.topic}\n\n用户反馈: {user_feedback}"
            next_stage = state.current_stage  # 重跑

        await self._persist_stage_update(state)
        return {
            "next_stage": next_stage,
            "stage_state": state.stage_state,
        }

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