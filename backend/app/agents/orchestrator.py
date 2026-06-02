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
from app.schemas.agent import OrchestratorInput, OrchestratorOutput, CollectorInput, CleanerInput, AnalyzerInput, ReporterInput, CleanedItem, Insight, CleanerOutput, AnalyzerOutput
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

        支持 start_stage / reentry_context / previous_output 从中间阶段重入流水线。
        """
        task_id = input_data.task_id
        topic = input_data.topic
        started_at = datetime.datetime.utcnow()

        start_stage = input_data.start_stage or "collecting"
        reentry_context = input_data.reentry_context
        previous_output = input_data.previous_output

        await self._update_status(task_id, "queued")

        collected_count = 0

        try:
            if start_stage == "collecting":
                # 1. Collecting Stage - 搜索 + 爬取数据源
                await self._update_status(task_id, "collecting")
                effective_topic = f"{topic} (搜索约束: {reentry_context})" if reentry_context else topic
                col_in = CollectorInput(task_id=task_id, topic=effective_topic, max_items=input_data.max_items)
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

                collected_count = len(col_out.items)

                # 3. Analyzing Stage - LLM 深度分析提取洞察
                await self._update_status(task_id, "analyzing")
                ana_in = AnalyzerInput(task_id=task_id, topic=topic, cleaned_items=cln_out.cleaned_items, dimensions=input_data.dimensions)
                ana_out = await self.analyzer.execute(ana_in)
                if not ana_out.success:
                    raise RuntimeError(f"Analyzer failed: {ana_out.error}")

                # 4. Reporting Stage - 生成结构化 Markdown 报告
                await self._update_status(task_id, "reporting")
                import re
                source_contents = []
                for ci in cln_out.cleaned_items:
                    full_text = "\n".join(ci.content_chunks) if ci.content_chunks else ci.summary
                    source_contents.append({
                        "uri": ci.source_uri,
                        "title": ci.title,
                        "content": full_text[:1000],
                    })
                rep_in = ReporterInput(
                    task_id=task_id, topic=topic, analyzer_output=ana_out,
                    include_charts=input_data.include_charts,
                    dimensions=input_data.dimensions,
                    source_contents=source_contents,
                )
                rep_out = await self.reporter.execute(rep_in)
                if not rep_out.success:
                    raise RuntimeError(f"Reporter failed: {rep_out.error}")

            elif start_stage == "analyzing":
                cleaned_data = (previous_output or {}).get("cleaned", {})
                cleaned_items_raw = cleaned_data.get("items", [])
                reconstructed_items = [
                    CleanedItem(
                        source_type=item.get("source_type", ""),
                        source_uri=item.get("source_uri", ""),
                        title=item.get("title", ""),
                        summary=item.get("summary", ""),
                        content_chunks=item.get("content_chunks", []),
                        relevance_score=item.get("relevance_score", 1.0),
                    )
                    for item in cleaned_items_raw
                ]
                cln_out = CleanerOutput(task_id=task_id, success=True, cleaned_items=reconstructed_items)
                collected_count = len(reconstructed_items)

                await self._update_status(task_id, "analyzing")
                analysis_topic = f"{topic}\n\n额外约束/反馈: {reentry_context}" if reentry_context else topic
                ana_in = AnalyzerInput(task_id=task_id, topic=analysis_topic, cleaned_items=cln_out.cleaned_items, dimensions=input_data.dimensions)
                ana_out = await self.analyzer.execute(ana_in)
                if not ana_out.success:
                    raise RuntimeError(f"Analyzer failed: {ana_out.error}")

                await self._update_status(task_id, "reporting")
                import re
                source_contents = []
                for ci in cln_out.cleaned_items:
                    full_text = "\n".join(ci.content_chunks) if ci.content_chunks else ci.summary
                    source_contents.append({
                        "uri": ci.source_uri,
                        "title": ci.title,
                        "content": full_text[:1000],
                    })
                rep_in = ReporterInput(
                    task_id=task_id, topic=topic, analyzer_output=ana_out,
                    include_charts=input_data.include_charts,
                    dimensions=input_data.dimensions,
                    source_contents=source_contents,
                )
                rep_out = await self.reporter.execute(rep_in)
                if not rep_out.success:
                    raise RuntimeError(f"Reporter failed: {rep_out.error}")

            elif start_stage == "reporting":
                cleaned_data = (previous_output or {}).get("cleaned", {})
                cleaned_items_raw = cleaned_data.get("items", [])
                reconstructed_items = [
                    CleanedItem(
                        source_type=item.get("source_type", ""),
                        source_uri=item.get("source_uri", ""),
                        title=item.get("title", ""),
                        summary=item.get("summary", ""),
                        content_chunks=item.get("content_chunks", []),
                        relevance_score=item.get("relevance_score", 1.0),
                    )
                    for item in cleaned_items_raw
                ]
                cln_out = CleanerOutput(task_id=task_id, success=True, cleaned_items=reconstructed_items)
                collected_count = len(reconstructed_items)

                analyzed_data = (previous_output or {}).get("analyzed", {})
                insights_raw = analyzed_data.get("insights", [])
                reconstructed_insights = [
                    Insight(
                        dimension=ins.get("dimension", ""),
                        analysis=ins.get("content", ""),
                        confidence=ins.get("confidence", 0.8),
                        evidence=ins.get("evidence", []),
                    )
                    for ins in insights_raw
                ]
                ana_out = AnalyzerOutput(
                    task_id=task_id,
                    success=True,
                    summary=analyzed_data.get("summary", ""),
                    insights=reconstructed_insights,
                )

                await self._update_status(task_id, "reporting")
                import re
                source_contents = []
                for ci in cln_out.cleaned_items:
                    full_text = "\n".join(ci.content_chunks) if ci.content_chunks else ci.summary
                    source_contents.append({
                        "uri": ci.source_uri,
                        "title": ci.title,
                        "content": full_text[:1000],
                    })
                rep_topic = f"{topic}\n\n报告生成额外要求: {reentry_context}" if reentry_context else topic
                rep_in = ReporterInput(
                    task_id=task_id, topic=rep_topic, analyzer_output=ana_out,
                    include_charts=input_data.include_charts,
                    dimensions=input_data.dimensions,
                    source_contents=source_contents,
                )
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
                collected_count=collected_count,
                cleaned_count=len(cln_out.cleaned_items),
                analyzer_output=ana_out,
                reporter_output=rep_out,
                error_message=None
            )

        except Exception as e:
            err_msg = str(e)
            await self._update_status(task_id, "failed", err_msg)
            ended_at = datetime.datetime.utcnow()

            partial = {}
            if 'col_out' in locals():
                partial["collected"] = {
                    "item_count": len(col_out.items),
                    "items": [{"title": it.title, "source_uri": it.source_uri} for it in col_out.items[:10]]
                }
            if 'cln_out' in locals():
                partial["cleaned"] = {
                    "item_count": len(cln_out.cleaned_items),
                    "items": [{"title": it.title, "source_uri": it.source_uri} for it in cln_out.cleaned_items[:10]]
                }
            if 'ana_out' in locals():
                partial["analyzed"] = {
                    "summary": ana_out.summary[:200],
                    "insight_count": len(ana_out.insights)
                }

            return OrchestratorOutput(
                task_id=task_id,
                topic=topic,
                status="failed",
                started_at=started_at,
                ended_at=ended_at,
                error_message=err_msg,
                partial_results=partial if partial else None
            )
