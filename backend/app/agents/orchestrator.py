import datetime
import logging
from typing import Optional, Callable, Awaitable
from app.schemas.agent import OrchestratorInput, OrchestratorOutput, CollectorInput, CleanerInput, AnalyzerInput, ReporterInput
from app.agents.collector import CollectorAgent
from app.agents.cleaner import CleanerAgent
from app.agents.analyzer import AnalyzerAgent
from app.agents.reporter import ReporterAgent

logger = logging.getLogger(__name__)

class OrchestratorAgent:
    def __init__(self, state_callback: Optional[Callable[[str, str, Optional[str]], Awaitable[None]]] = None):
        self.collector = CollectorAgent()
        self.cleaner = CleanerAgent()
        self.analyzer = AnalyzerAgent()
        self.reporter = ReporterAgent()
        self.state_callback = state_callback # async def callback(task_id: str, status: str, error: Optional[str] = None)

    async def _update_status(self, task_id: str, status: str, error: Optional[str] = None):
        logger.info(f"[Task {task_id}] Status transition -> {status}" + (f" (Error: {error})" if error else ""))
        if self.state_callback:
            try:
                await self.state_callback(task_id, status, error)
            except Exception as e:
                logger.error(f"Failed to execute state_callback for task {task_id}: {str(e)}")

    async def execute(self, input_data: OrchestratorInput) -> OrchestratorOutput:
        task_id = input_data.task_id
        topic = input_data.topic
        started_at = datetime.datetime.utcnow()

        await self._update_status(task_id, "queued")

        try:
            # 1. Collecting Stage
            await self._update_status(task_id, "collecting")
            col_in = CollectorInput(task_id=task_id, topic=topic, max_items=input_data.max_items)
            col_out = await self.collector.execute(col_in)
            if not col_out.success:
                raise RuntimeError(f"Collector failed: {col_out.error}")

            # 2. Cleaning Stage
            await self._update_status(task_id, "cleaning")
            cln_in = CleanerInput(task_id=task_id, raw_items=col_out.items)
            self.cleaner.min_content_length = input_data.min_content_length
            cln_out = await self.cleaner.execute(cln_in)
            if not cln_out.success:
                raise RuntimeError(f"Cleaner failed: {cln_out.error}")

            # 3. Analyzing Stage
            await self._update_status(task_id, "analyzing")
            ana_in = AnalyzerInput(task_id=task_id, topic=topic, cleaned_items=cln_out.cleaned_items)
            ana_out = await self.analyzer.execute(ana_in)
            if not ana_out.success:
                raise RuntimeError(f"Analyzer failed: {ana_out.error}")

            # 4. Reporting Stage
            await self._update_status(task_id, "reporting")
            rep_in = ReporterInput(task_id=task_id, topic=topic, analyzer_output=ana_out, include_charts=input_data.include_charts)
            rep_out = await self.reporter.execute(rep_in)
            if not rep_out.success:
                raise RuntimeError(f"Reporter failed: {rep_out.error}")

            # 5. Completed
            await self._update_status(task_id, "completed")
            ended_at = datetime.datetime.utcnow()

            return OrchestratorOutput(
                task_id=task_id,
                topic=topic,
                status="completed",
                started_at=started_at,
                ended_at=ended_at,
                collected_count=len(col_out.items),
                cleaned_count=len(cln_out.cleaned_items),
                analyzer_output=ana_out,
                reporter_output=rep_out,
                error_message=None
            )

        except Exception as e:
            err_msg = str(e)
            await self._update_status(task_id, "failed", err_msg)
            ended_at = datetime.datetime.utcnow()
            return OrchestratorOutput(
                task_id=task_id,
                topic=topic,
                status="failed",
                started_at=started_at,
                ended_at=ended_at,
                error_message=err_msg
            )
