"""
OrchestratorAgent（主控 Agent）

职责：
- 串联 Collector → Cleaner → Analyzer → Reporter 四阶段流水线
- 每个阶段通过 state_callback 回调通知外部任务状态变更
- 任一阶段失败即中止后续流程，返回带 error_message 的失败结果

为什么需要 state_callback：
- 前端需要实时感知任务进度（queued → collecting → cleaning → analyzing → reporting → completed/failed）
- 通过回调将状态变更写入数据库，实现流水线的可观测性
"""

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
        """
        state_callback: 异步回调 async def callback(task_id: str, status: str, error: Optional[str] = None)
        用于在每个阶段开始/结束时通知外部系统更新任务状态
        """
        self.collector = CollectorAgent()
        self.cleaner = CleanerAgent()
        self.analyzer = AnalyzerAgent()
        self.reporter = ReporterAgent()
        self.state_callback = state_callback

    async def _update_status(self, task_id: str, status: str, error: Optional[str] = None):
        """通过回调通知状态变更，同时写入本地日志"""
        logger.info(f"[Task {task_id}] Status transition -> {status}" + (f" (Error: {error})" if error else ""))
        if self.state_callback:
            try:
                await self.state_callback(task_id, status, error)
            except Exception as e:
                logger.error(f"Failed to execute state_callback for task {task_id}: {str(e)}")

    async def execute(self, input_data: OrchestratorInput) -> OrchestratorOutput:
        """
        执行完整的四阶段分析流水线：
        ① collecting → ② cleaning → ③ analyzing → ④ reporting

        每个阶段成功后传递数据到下一阶段，失败则立即终止并返回错误。
        """
        task_id = input_data.task_id
        topic = input_data.topic
        started_at = datetime.datetime.utcnow()

        await self._update_status(task_id, "queued")

        try:
            # 1. Collecting Stage - 搜索 + 爬取数据源
            await self._update_status(task_id, "collecting")
            col_in = CollectorInput(task_id=task_id, topic=topic, max_items=input_data.max_items)
            col_out = await self.collector.execute(col_in)
            if not col_out.success:
                raise RuntimeError(f"Collector failed: {col_out.error}")

            # 2. Cleaning Stage - 去重、过滤低质内容、分块
            await self._update_status(task_id, "cleaning")
            cln_in = CleanerInput(task_id=task_id, raw_items=col_out.items)
            self.cleaner.min_content_length = input_data.min_content_length
            cln_out = await self.cleaner.execute(cln_in)
            if not cln_out.success:
                raise RuntimeError(f"Cleaner failed: {cln_out.error}")

            # 3. Analyzing Stage - LLM 深度分析提取洞察
            await self._update_status(task_id, "analyzing")
            ana_in = AnalyzerInput(task_id=task_id, topic=topic, cleaned_items=cln_out.cleaned_items)
            ana_out = await self.analyzer.execute(ana_in)
            if not ana_out.success:
                raise RuntimeError(f"Analyzer failed: {ana_out.error}")

            # 4. Reporting Stage - 生成结构化 Markdown 报告
            await self._update_status(task_id, "reporting")
            rep_in = ReporterInput(task_id=task_id, topic=topic, analyzer_output=ana_out, include_charts=input_data.include_charts)
            rep_out = await self.reporter.execute(rep_in)
            if not rep_out.success:
                raise RuntimeError(f"Reporter failed: {rep_out.error}")

            # 5. Completed - 所有阶段成功完成
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
