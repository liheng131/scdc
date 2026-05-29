"""
智能体工作流引擎

提供简化的市场洞察工作流执行。
状态流: idle → running(收集→清洗→分析→报告) → completed

前端以对话形式展示，仅显示最终报告结果。
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional, AsyncGenerator

from app.schemas.agent import CollectorInput, CleanerInput, AnalyzerInput, ReporterInput

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

class WorkflowService:
    def __init__(self):
        self._workflows: Dict[str, WorkflowState] = {}

    def create_workflow(self, topic: str, max_items: int, dimensions: list = None) -> WorkflowState:
        wf_id = str(uuid.uuid4())[:8]
        if dimensions is None:
            dimensions = []
        state = WorkflowState(wf_id, topic, max_items, dimensions)
        self._workflows[wf_id] = state
        return state

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        return self._workflows.get(workflow_id)

    async def run_workflow_stream(self, state: WorkflowState) -> AsyncGenerator[str, None]:
        try:
            state.status = "running"
            collect_output = None
            clean_output = None
            analyze_output = None

            for idx, stage_name in enumerate(STAGE_SEQUENCE):
                state.current_stage = stage_name
                state.current_stage_index = idx

                yield self._sse("stage_start", {
                    "stage": stage_name,
                    "label": STAGE_LABELS[stage_name],
                    "icon": STAGE_ICONS[stage_name],
                    "index": idx,
                    "total": 4,
                })

                try:
                    if stage_name == "collecting":
                        result = await self._run_collect(state)
                        collect_output = result
                        state.stages["collecting"] = {
                            "item_count": len(result.items) if result.items else 0,
                        }
                    elif stage_name == "cleaning":
                        result = await self._run_clean(state, collect_output)
                        clean_output = result
                        state.stages["cleaning"] = {
                            "before_count": len(collect_output.items) if collect_output.items else 0,
                            "after_count": len(result.cleaned_items) if result.cleaned_items else 0,
                        }
                    elif stage_name == "analyzing":
                        result = await self._run_analyze(state, clean_output)
                        analyze_output = result
                        state.stages["analyzing"] = {
                            "insight_count": len(result.insights) if result.insights else 0,
                        }
                    elif stage_name == "reporting":
                        result = await self._run_report(state, analyze_output, clean_output)
                        state.stages["reporting"] = {
                            "report_markdown": result.markdown_report,
                            "chart_configs": result.chart_configs,
                            "sections": [{"title": s.title, "content": s.content} for s in result.sections],
                        }
                        state.result = state.stages["reporting"]
                except Exception as e:
                    logger.error(f"Stage {stage_name} failed: {e}", exc_info=True)
                    state.error = str(e)
                    state.status = "failed"
                    yield self._sse("stage_error", {
                        "stage": stage_name,
                        "label": STAGE_LABELS[stage_name],
                        "error": str(e)[:500],
                    })
                    return

                yield self._sse("stage_complete", {
                    "stage": stage_name,
                    "label": STAGE_LABELS[stage_name],
                })

            state.status = "completed"
            report_data = state.result or {}
            yield self._sse("completed", {
                "workflow_id": state.workflow_id,
                "topic": state.topic,
                "report_markdown": report_data.get("report_markdown", ""),
                "chart_configs": report_data.get("chart_configs", []),
                "sections": report_data.get("sections", []),
            })

        except Exception as e:
            logger.error(f"Workflow {state.workflow_id} failed: {e}", exc_info=True)
            state.status = "failed"
            state.error = str(e)
            yield self._sse("error", {"error": str(e)[:500]})

    async def _run_collect(self, state: WorkflowState):
        from app.agents.collector import CollectorAgent
        agent = CollectorAgent()
        return await agent.execute(CollectorInput(
            task_id=state.workflow_id,
            topic=state.topic,
            max_items=state.max_items,
        ))

    async def _run_clean(self, state: WorkflowState, collect_output):
        from app.agents.cleaner import CleanerAgent
        agent = CleanerAgent()
        return await agent.execute(CleanerInput(
            task_id=state.workflow_id,
            raw_items=collect_output.items if collect_output else [],
        ))

    async def _run_analyze(self, state: WorkflowState, clean_output):
        from app.agents.analyzer import AnalyzerAgent
        agent = AnalyzerAgent()
        return await agent.execute(AnalyzerInput(
            task_id=state.workflow_id,
            topic=state.topic,
            cleaned_items=clean_output.cleaned_items if clean_output else [],
            dimensions=state.dimensions,
        ))

    async def _run_report(self, state: WorkflowState, analyze_output, clean_output):
        from app.agents.reporter import ReporterAgent
        import re
        
        def _sanitize(text):
            text = re.sub(r'[^\x20-\x7E\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\n\r\t]', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        
        agent = ReporterAgent()
        
        source_contents = []
        if clean_output and clean_output.cleaned_items:
            for ci in clean_output.cleaned_items:
                full_text = "\n".join(ci.content_chunks) if ci.content_chunks else ci.summary
                safe_content = _sanitize(full_text)
                if safe_content:
                    source_contents.append({
                        "uri": ci.source_uri,
                        "title": _sanitize(ci.title) or ci.title,
                        "content": safe_content[:1000],
                    })
        
        return await agent.execute(ReporterInput(
            task_id=state.workflow_id,
            topic=state.topic,
            analyzer_output=analyze_output,
            include_charts=True,
            dimensions=state.dimensions,
            source_contents=source_contents,
        ))

    def _sse(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    def get_history(self) -> list:
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