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
from app.schemas.agent import OrchestratorInput, OrchestratorOutput, CollectorInput, CleanerInput, AnalyzerInput, ReporterInput, CleanedItem, Insight, CleanerOutput, AnalyzerOutput, DEFAULT_DIMENSIONS
from app.agents.collector import CollectorAgent
from app.agents.cleaner import CleanerAgent
from app.agents.analyzer import AnalyzerAgent
from app.agents.reporter import ReporterAgent
from app.services.dimension_generator import DimensionGenerator

logger = logging.getLogger(__name__)

class OrchestratorAgent:
    def __init__(self, state_callback: Optional[Callable] = None):
        """
        state_callback: 异步回调 async def callback(task_id, status, error=None, stage_detail=None)
        - task_id: 任务 ID
        - status: 阶段名 (collecting/cleaning/analyzing/reporting/...)
        - error: 错误信息(可选)
        - stage_detail: dict 包含 summary + detail,用于阶段详情弹窗
                       例如 {"summary": {"insight_count": 10}, "detail": {"insights": [...]}}
        """
        self.collector = CollectorAgent()
        self.cleaner = CleanerAgent()
        self.analyzer = AnalyzerAgent()
        self.reporter = ReporterAgent()
        self.dimension_generator = DimensionGenerator()
        self.state_callback = state_callback
        # 阶段产出缓存: {stage_name: {summary, detail}}
        # 在每个阶段执行完毕后填充,在 _update_status 切换状态时附带传出
        self._stage_outputs: dict = {}

    def _build_stage_detail(self, stage: str) -> Optional[dict]:
        """从 self._stage_outputs 取出指定阶段的产出,转为 {summary, detail} 格式"""
        out = self._stage_outputs.get(stage)
        if not out:
            return None
        return {"summary": out.get("summary", {}), "detail": out.get("detail", {})}

    @staticmethod
    def _previous_stage(current: str) -> Optional[str]:
        """根据当前阶段名,返回上一阶段名(用于在状态切换时附带上一阶段的 detail)"""
        order = ["collecting", "cleaning", "analyzing", "reporting"]
        try:
            idx = order.index(current)
        except ValueError:
            return None
        if idx <= 0:
            return None
        return order[idx - 1]

    async def _update_status(self, task_id: str, status: str, error: Optional[str] = None, stage_detail: Optional[dict] = None):
        """通过回调通知状态变更，同时写入本地日志

        Args:
            stage_detail: 上一阶段产出的 {summary, detail},在阶段切换时传出
                         (由 run_workflow_stream 在 yield stage_complete 时填入 detail 字段)
                         如果未显式传入,会自动从 self._stage_outputs 推导上一阶段的 detail
        """
        logger.info(f"[Task {task_id}] Status transition -> {status}" + (f" (Error: {error})" if error else ""))
        if self.state_callback:
            # 自动推导上一阶段的 detail(若未显式传入)
            if stage_detail is None:
                prev = self._previous_stage(status)
                if prev:
                    stage_detail = self._build_stage_detail(prev)
            try:
                await self.state_callback(task_id, status, error, stage_detail)
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

                # 缓存 collecting 阶段产出(供 stage_complete 事件使用)
                self._stage_outputs["collecting"] = {
                    "summary": {
                        "item_count": len(col_out.items),
                        "keywords_count": len(col_out.expanded_keywords or []),
                        "total_search_results": len(col_out.items),  # 去重后 = col_out.items
                    },
                    "detail": {
                        "keywords": list(col_out.expanded_keywords or []),
                        "items": [
                            {"title": it.title, "source_uri": it.source_uri, "snippet": (it.content or "")[:200]}
                            for it in col_out.items[:30]
                        ],
                    },
                }

                # 2. Cleaning Stage - 去重、过滤低质内容、分块
                await self._update_status(task_id, "cleaning")
                cln_in = CleanerInput(task_id=task_id, raw_items=col_out.items)
                self.cleaner.min_content_length = input_data.min_content_length
                cln_out = await self.cleaner.execute(cln_in)
                if not cln_out.success:
                    raise RuntimeError(f"Cleaner failed: {cln_out.error}")

                collected_count = len(col_out.items)

                # 缓存 cleaning 阶段产出
                total_in = len(col_out.items)  # Cleaner 输入 = Collector 输出
                total_out = len(cln_out.cleaned_items)
                self._stage_outputs["cleaning"] = {
                    "summary": {
                        "total_in": total_in,
                        "total_out": total_out,
                        "removed_count": max(0, total_in - total_out),
                    },
                    "detail": {
                        "stats": {"total_in": total_in, "total_out": total_out},
                        "cleaning_summary": f"清洗前 {total_in} 条 → 清洗后 {total_out} 条,移除 {max(0, total_in - total_out)} 条",
                    },
                }

                # 3. Analyzing Stage - LLM 深度分析提取洞察
                await self._update_status(task_id, "analyzing")
                # 动态生成主题相关的分析维度
                try:
                    if input_data.dimensions:
                        # OrchestratorInput 显式传入了 dimensions(用户强制指定),尊重用户
                        dynamic_dims = list(input_data.dimensions)
                        logger.info(f"Orchestrator using user-specified dimensions: {dynamic_dims}")
                    else:
                        # 调用 DimensionGenerator 动态生成
                        dynamic_dims = await self.dimension_generator.generate(topic, min_dim=4, max_dim=6)
                        logger.info(f"Orchestrator using dynamically generated dimensions: {dynamic_dims}")
                except Exception as e:
                    # 任何异常都不阻塞主流程,回退到默认
                    logger.warning(f"DimensionGenerator failed, using defaults: {e}")
                    dynamic_dims = list(DEFAULT_DIMENSIONS)
                ana_in = AnalyzerInput(
                    task_id=task_id,
                    topic=topic,
                    cleaned_items=cln_out.cleaned_items,
                    dimensions=dynamic_dims,
                    expanded_keywords=col_out.expanded_keywords,
                )
                ana_out = await self.analyzer.execute(ana_in)
                if not ana_out.success:
                    raise RuntimeError(f"Analyzer failed: {ana_out.error}")

                # 缓存 analyzing 阶段产出(关键:供前端 stageDetails.analyzing.detail 使用)
                # 序列化时合并 conclusion + analysis,确保 LLM 只写一个字段时也有内容可显示
                dims = sorted({i.dimension for i in ana_out.insights if i.dimension})
                insights_serialized = []
                for i in ana_out.insights:
                    # 本地模型经常只填 conclusion,analysis 留空;合并到 content 字段
                    body = i.analysis.strip() if i.analysis else ""
                    headline = i.conclusion.strip() if i.conclusion else ""
                    if body and headline and headline not in body:
                        content = f"{headline}\n\n{body}"
                    else:
                        content = body or headline
                    insights_serialized.append({
                        "dimension": i.dimension,
                        "title": headline[:80] if headline else "",
                        "content": content,
                        "evidence": list(i.evidence or []),
                        "confidence": i.confidence,
                    })
                rag_serialized = [
                    {
                        "title": r.get("title", ""),
                        "content_snippet": r.get("content_snippet", ""),
                        "relevance_score": r.get("relevance_score", 0.0),
                    }
                    for r in (ana_out.rag_results or [])
                ]
                self._stage_outputs["analyzing"] = {
                    "summary": {
                        "insight_count": len(ana_out.insights),
                        "dimensions": dims,
                        "rag_results_count": ana_out.rag_results_count,
                    },
                    "detail": {
                        "insights": insights_serialized,
                        "dimensions": dims,
                        "rag_results_count": ana_out.rag_results_count,
                        "rag_results": rag_serialized,
                    },
                }

                # 4. Reporting Stage - 生成结构化 Markdown 报告
                await self._update_status(task_id, "reporting")
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
                    dimensions=dynamic_dims,
                    source_contents=source_contents,
                )
                rep_out = await self.reporter.execute(rep_in)
                if not rep_out.success:
                    raise RuntimeError(f"Reporter failed: {rep_out.error}")

                # 缓存 reporting 阶段产出
                self._stage_outputs["reporting"] = {
                    "summary": {
                        "report_length": len(rep_out.markdown_report or ""),
                        "chart_count": len(rep_out.chart_configs or []),
                    },
                    "detail": {
                        "report_markdown": rep_out.markdown_report or "",
                        "chart_count": len(rep_out.chart_configs or []),
                        "chart_configs": rep_out.chart_configs or [],
                        "sections": [
                            {"title": s.title, "content": s.content}
                            for s in (rep_out.sections or [])
                        ],
                    },
                }

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
                # reentry 也需要动态维度:优先复用 previous_output.dimensions,否则重新生成
                try:
                    cached_dims = (previous_output or {}).get("dimensions")
                    if cached_dims:
                        dynamic_dims = list(cached_dims)
                        logger.info(f"Reusing cached dimensions from previous run: {dynamic_dims}")
                    elif input_data.dimensions:
                        dynamic_dims = list(input_data.dimensions)
                    else:
                        dynamic_dims = await self.dimension_generator.generate(analysis_topic, min_dim=4, max_dim=6)
                except Exception as e:
                    logger.warning(f"Reentry dimension resolution failed, using defaults: {e}")
                    dynamic_dims = list(DEFAULT_DIMENSIONS)
                expanded_keywords = (previous_output or {}).get("expanded_keywords", [])
                ana_in = AnalyzerInput(
                    task_id=task_id,
                    topic=analysis_topic,
                    cleaned_items=cln_out.cleaned_items,
                    dimensions=dynamic_dims,
                    expanded_keywords=expanded_keywords,
                )
                ana_out = await self.analyzer.execute(ana_in)
                if not ana_out.success:
                    raise RuntimeError(f"Analyzer failed: {ana_out.error}")

                # 缓存 analyzing 阶段产出(reentry 路径同样需要)
                # 序列化时合并 conclusion + analysis
                dims = sorted({i.dimension for i in ana_out.insights if i.dimension})
                insights_serialized = []
                for i in ana_out.insights:
                    body = i.analysis.strip() if i.analysis else ""
                    headline = i.conclusion.strip() if i.conclusion else ""
                    if body and headline and headline not in body:
                        content = f"{headline}\n\n{body}"
                    else:
                        content = body or headline
                    insights_serialized.append({
                        "dimension": i.dimension,
                        "title": headline[:80] if headline else "",
                        "content": content,
                        "evidence": list(i.evidence or []),
                        "confidence": i.confidence,
                    })
                rag_serialized = [
                    {
                        "title": r.get("title", ""),
                        "content_snippet": r.get("content_snippet", ""),
                        "relevance_score": r.get("relevance_score", 0.0),
                    }
                    for r in (ana_out.rag_results or [])
                ]
                self._stage_outputs["analyzing"] = {
                    "summary": {
                        "insight_count": len(ana_out.insights),
                        "dimensions": dims,
                        "rag_results_count": ana_out.rag_results_count,
                    },
                    "detail": {
                        "insights": insights_serialized,
                        "dimensions": dims,
                        "rag_results_count": ana_out.rag_results_count,
                        "rag_results": rag_serialized,
                    },
                }

                await self._update_status(task_id, "reporting")
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
                    dimensions=dynamic_dims,
                    source_contents=source_contents,
                    web_images=col_out.extracted_images or [],
                )
                rep_out = await self.reporter.execute(rep_in)
                if not rep_out.success:
                    raise RuntimeError(f"Reporter failed: {rep_out.error}")

                # 缓存 reporting 阶段产出
                self._stage_outputs["reporting"] = {
                    "summary": {
                        "report_length": len(rep_out.markdown_report or ""),
                        "chart_count": len(rep_out.chart_configs or []),
                    },
                    "detail": {
                        "report_markdown": rep_out.markdown_report or "",
                        "chart_count": len(rep_out.chart_configs or []),
                        "chart_configs": rep_out.chart_configs or [],
                        "sections": [
                            {"title": s.title, "content": s.content}
                            for s in (rep_out.sections or [])
                        ],
                    },
                }

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

                # reentry reporting 路径下也回填 analyzing 阶段产出,供前端弹窗显示
                # 序列化时合并 conclusion + analysis
                dims_reentry = sorted({i.dimension for i in reconstructed_insights if i.dimension})
                insights_reentry = []
                for i in reconstructed_insights:
                    body = i.analysis.strip() if i.analysis else ""
                    headline = i.conclusion.strip() if i.conclusion else ""
                    if body and headline and headline not in body:
                        content = f"{headline}\n\n{body}"
                    else:
                        content = body or headline
                    insights_reentry.append({
                        "dimension": i.dimension,
                        "title": headline[:80] if headline else "",
                        "content": content,
                        "evidence": list(i.evidence or []),
                        "confidence": i.confidence,
                    })
                self._stage_outputs["analyzing"] = {
                    "summary": {
                        "insight_count": len(reconstructed_insights),
                        "dimensions": dims_reentry,
                        "rag_results_count": 0,
                    },
                    "detail": {
                        "insights": insights_reentry,
                        "dimensions": dims_reentry,
                        "rag_results_count": 0,
                        "rag_results": [],
                    },
                }

                await self._update_status(task_id, "reporting")
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
                    task_id=task_id, topic=topic, analyzer_output=ana_out,
                    include_charts=input_data.include_charts,
                    dimensions=dynamic_dims,
                    source_contents=source_contents,
                    web_images=col_out.extracted_images or [],
                )
                rep_out = await self.reporter.execute(rep_in)
                if not rep_out.success:
                    raise RuntimeError(f"Reporter failed: {rep_out.error}")

                # 缓存 reporting 阶段产出
                self._stage_outputs["reporting"] = {
                    "summary": {
                        "report_length": len(rep_out.markdown_report or ""),
                        "chart_count": len(rep_out.chart_configs or []),
                    },
                    "detail": {
                        "report_markdown": rep_out.markdown_report or "",
                        "chart_count": len(rep_out.chart_configs or []),
                        "chart_configs": rep_out.chart_configs or [],
                        "sections": [
                            {"title": s.title, "content": s.content}
                            for s in (rep_out.sections or [])
                        ],
                    },
                }

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
