"""
AnalyzerAgent（AI 分析 Agent）

职责：
- 接收 CleanerAgent 清洗后的数据，调用 Ollama LLM 进行分析
- 将清洗后的内容拼接为结构化 Prompt，要求 LLM 返回 JSON 格式的分析结果
- LLM 不可用时自动降级为基于规则的分析（rule-based degradation）

为什么使用 Ollama：
- 完全本地部署，数据不出内网，满足企业安全合规要求
- 无需 API 费用，适合持续集成和批量分析

为什么设计降级策略：
- LLM 服务可能因 GPU 资源不足、网络故障等原因不可用
- 降级到规则分析确保系统在 LLM 故障时仍能产出可用结果，不中断流水线
"""

import asyncio
import json
import logging
import re
import traceback
import httpx
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.schemas.agent import (
    AnalyzerInput, AnalyzerOutput, Insight, CleanedItem,
    StructuredMetric, MetricDataPoint,
)
from app.core.config import settings
from app.core.runtime_config import rumtime_config
from app.services.embedding import EmbeddingService
from app.services.vectorstore import VectorStoreService
from app.services.rerank import RerankService

logger = logging.getLogger(__name__)


def _sanitize_text(text: str, max_len: int = 300) -> str:
    text = re.sub(r'[^\x20-\x7E\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\n\r\t]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len]


# 维度 -> 图表类型映射（用于分析阶段生成 chart_plan）
DIMENSION_CHART_MAP: Dict[str, str] = {
    "宏观经济环境": "bar",
    "宏观经济": "bar",
    "行业形势与趋势": "line",
    "行业趋势": "line",
    "竞争格局与对手": "comparison",
    "竞争格局": "comparison",
    "细分板块分析": "pie",
    "细分板块": "pie",
}


def _build_chart_plan(insights: List["Insight"]) -> List[Dict[str, Any]]:
    """根据 insights 的 dimension 字段生成图表规划。

    每个 insight 维度对应一种图表类型，便于 Reporter 阶段渲染。
    data_points 在 Reporter 阶段填充。

    对每个 insight 同时生成:
    - 一张 "section_start" 概览图(默认用 bar/line/pie/comparison 之一)
    - 一张 "section_end" 详细图(支持 table/matrix/flow 等其它类型)

    这样 Reporter 既能在章节开头给出可视化概览,也能在章节末尾给出补充图表。
    """
    chart_plan: List[Dict[str, Any]] = []
    for insight in insights:
        dim = insight.dimension or "综合分析"
        chart_type = DIMENSION_CHART_MAP.get(dim, "bar")
        description_src = insight.analysis or insight.conclusion or ""

        # 概览图:章节开头 - 直观展示该维度的核心数据
        chart_plan.append({
            "dimension": dim,
            "chart_type": chart_type,
            "title": f"{dim}分析概览",
            "data_points": [],
            "position": "section_start",
            "description": description_src[:100],
        })

        # 详细图:章节末尾 - 表格 / 矩阵 / 流程图
        # 推断详细图类型: 数字/指标类 -> table, 多维 -> matrix, 链路/关系 -> flow
        detail_type = "table"
        dim_l = (dim or "").lower()
        if any(kw in dim for kw in ["矩阵", "能力", "画像", "评估"]):
            detail_type = "matrix"
        elif any(kw in dim for kw in ["流程", "链路", "path", "flow", "周期"]):
            detail_type = "flow"
        chart_plan.append({
            "dimension": dim,
            "chart_type": detail_type,
            "title": f"{dim}详细数据",
            "data_points": [],
            "position": "section_end",
            "description": description_src[:100],
        })
    return chart_plan


class AnalyzerAgent:
    def __init__(self):
        self.llm_provider = rumtime_config.get("llm_provider")
        self.default_model = rumtime_config.get("default_model")
        self.llm_base_url = rumtime_config.get("llm_base_url")
        self.llm_api_key = settings.llm_api_key
        self._db_config_loaded = False

        self._build_llm_config()

    def _build_llm_config(self):
        if self.llm_provider == "gpustack":
            self.llm_url = f"{self.llm_base_url.rstrip('/')}/v1/chat/completions"
            self.headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.llm_url = f"{self.llm_base_url.rstrip('/')}/api/generate"
            self.headers = {}

    async def _ensure_db_config(self):
        if self._db_config_loaded:
            return
        self._db_config_loaded = True
        try:
            db_config = await rumtime_config.get_default_model_config("llm")
            if db_config:
                self.llm_provider = db_config["provider"].lower() if db_config["provider"] else self.llm_provider
                self.default_model = db_config["model_name"] or self.default_model
                if db_config["base_url"]:
                    self.llm_base_url = db_config["base_url"]
                if db_config["api_key"]:
                    self.llm_api_key = db_config["api_key"]
                self._build_llm_config()
        except Exception:
            pass

    def _build_prompt(self, topic: str, items: List[CleanedItem], dimensions: List[str], context_snippets: List[str] = None) -> str:
        context_parts = []
        for i, item in enumerate(items):
            full_text = "\n".join(item.content_chunks) if item.content_chunks else item.summary
            if len(full_text) > 1500:
                full_text = full_text[:1500] + "..."
            context_parts.append(
                f"--- Source #{i+1} ---\n"
                f"URI: {item.source_uri}\n"
                f"Title: {item.title}\n"
                f"Content:\n{full_text}\n"
            )

        context_str = "\n".join(context_parts)

        dim_labels = "\n".join(f"  - {d}" for d in dimensions)
        dim_slots = ", ".join(f'"{d}"' for d in dimensions)

        historical_section = ""
        if context_snippets:
            snippets_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(context_snippets))
            historical_section = f"""## 历史相关报告背景
以下是之前相关报告中的关键背景信息片段，可用于了解历史上下文和趋势：
{snippets_str}

"""

        prompt = f"""You are a senior market intelligence analyst with decades of experience at a top-tier consulting firm.

Your task: produce a deep, insightful analysis of the topic "{topic}" based on the source materials below.

The analysis MUST be structured into the following dimensions (do NOT use any other dimension labels):
{dim_labels}

{historical_section}REQUIREMENTS:
1. Write a substantive executive summary (200-400 words) that synthesizes findings into a coherent narrative, covering ALL the dimensions above. Include key numbers, specific company names, and directional trends where available.
2. For EACH dimension above, extract **at least 3** insights (target 3-5 per dimension). Total 10-20 insights across all dimensions. If data is insufficient, prefer 3-4 per dimension with caveats. For EACH insight:
   - "conclusion": a one-sentence headline
   - "analysis": 2-4 sentence deep dive explaining the evidence, implications, and why it matters (80-150 words)
   - "evidence": URIs from the sources that support this insight
   - "confidence": your certainty level (0.0-1.0)
   - "dimension": MUST be exactly one of [{dim_slots}]
3. Cross-reference sources where possible - if two sources reinforce the same finding, mention that in the analysis.
4. Be specific and data-driven. Avoid vague generalities like "the market is growing."
5. Every dimension listed above MUST have at least one insight. Do not leave any dimension uncovered.
6. Extract structured metrics from the source materials for chart generation. For each quantifiable finding, output a structured_metrics entry. Focus on:
   - Yearly trends (e.g., 2020-2025 market size by year)
   - Quarterly/Monthly breakdowns if available
   - Year-over-year (YoY) or Quarter-over-Quarter (QoQ) growth rates
   - Market share distributions (percentages per company/segment)
   - Regional breakdowns or category comparisons
   Each structured_metric MUST have: metric_name, metric_type (yearly_trend/quarterly_trend/monthly_trend/yoy_growth/qoq_growth/market_share/other), unit, dimension, data_points (list of objects with label and value fields), source, chart_type_hint (bar/line/pie).

Output strictly as JSON, no markdown:
{{
  "summary": "detailed executive summary covering all dimensions above (200-400 words)",
  "insights": [
    {{
      "conclusion": "one-sentence headline",
      "analysis": "2-4 sentence deep-dive with evidence, implications, significance (80-150 words)",
      "evidence": ["uri1", "uri2"],
      "confidence": 0.92,
      "dimension": "{dimensions[0] if dimensions else ''}"
    }}
  ],
  "structured_metrics": [
    {{
      "metric_name": "AI芯片市场规模",
      "metric_type": "yearly_trend",
      "unit": "亿美元",
      "dimension": "{dimensions[0] if dimensions else ''}",
      "data_points": [
        {{"label": "2020", "value": 450}},
        {{"label": "2021", "value": 580}},
        {{"label": "2022", "value": 720}}
      ],
      "source": "source_material_title",
      "chart_type_hint": "line"
    }}
  ]
}}

SOURCE MATERIALS:
{context_str}"""
        return prompt

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, json.JSONDecodeError)),
        reraise=True
    )
    async def _call_llm(self, prompt: str, timeout: int = 120) -> Dict[str, Any]:
        if self.llm_provider == "gpustack":
            payload = {
                "model": self.default_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": rumtime_config.get("temperature"),
                "max_tokens": rumtime_config.get("max_tokens"),
            }
        else:
            payload = {
                "model": self.default_model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": rumtime_config.get("temperature")}
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.llm_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            
            if self.llm_provider == "gpustack":
                response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                response_text = data.get("response", "")
            
            response_text = self._clean_json_response(response_text)
            if not response_text:
                raise json.JSONDecodeError("Empty response after cleaning", "", 0)
            return json.loads(response_text)

    def _clean_json_response(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _parse_structured_metrics(self, raw_metrics: list) -> List[StructuredMetric]:
        """Parse StructuredMetric objects from raw LLM JSON output"""
        result: List[StructuredMetric] = []
        if not raw_metrics or not isinstance(raw_metrics, list):
            return result

        valid_types = {
            "yearly_trend", "quarterly_trend", "monthly_trend",
            "yoy_growth", "qoq_growth", "market_share", "other",
        }
        for rm in raw_metrics:
            if not isinstance(rm, dict):
                continue
            data_points = []
            for dp in rm.get("data_points", []) or []:
                if not isinstance(dp, dict):
                    continue
                try:
                    data_points.append(MetricDataPoint(
                        label=str(dp.get("label", "")),
                        value=float(dp.get("value", 0)),
                    ))
                except (ValueError, TypeError):
                    continue

            if len(data_points) < 2:
                continue  # 至少需要 2 个数据点才能绘图

            metric_type = str(rm.get("metric_type", "other")).lower()
            if metric_type not in valid_types:
                metric_type = "other"

            chart_hint = str(rm.get("chart_type_hint", "bar")).lower()
            if chart_hint not in ("bar", "line", "pie"):
                # 自动推断：时序数据用 line，占比用 pie
                if metric_type in ("market_share",):
                    chart_hint = "pie"
                elif metric_type.endswith("_trend"):
                    chart_hint = "line"
                else:
                    chart_hint = "bar"

            result.append(StructuredMetric(
                metric_name=str(rm.get("metric_name", "未命名指标")),
                metric_type=metric_type,
                unit=str(rm.get("unit", "")),
                dimension=str(rm.get("dimension", "")),
                data_points=data_points,
                source=str(rm.get("source", "")),
                chart_type_hint=chart_hint,
            ))

        return result

    def _extract_metrics_from_text(self, text: str, dimensions: List[str]) -> List[StructuredMetric]:
        """Extract numeric values and years from text using regex, generate basic structured metrics (fallback)"""
        metrics: List[StructuredMetric] = []
        if not text:
            return metrics

        # 匹配 年份:数值 模式，如 "2020年: 450亿美元" 或 "2020年达到450亿"
        year_value_pattern = re.findall(
            r'(20\d{2})\s*年[^0-9]*?(\d+(?:\.\d+)?)\s*(亿|万|%|美元|亿元|万元)?',
            text,
        )
        if len(year_value_pattern) >= 2:
            data_points = []
            unit = ""
            for y, v, u in year_value_pattern:
                try:
                    data_points.append(MetricDataPoint(label=y, value=float(v)))
                    if u:
                        unit = u
                except ValueError:
                    continue
            if len(data_points) >= 2:
                metrics.append(StructuredMetric(
                    metric_name="年度趋势",
                    metric_type="yearly_trend",
                    unit=unit,
                    dimension=dimensions[0] if dimensions else "",
                    data_points=data_points,
                    source="从文本中提取",
                    chart_type_hint="line",
                ))

        # 匹配 占比数据，如 "占比35%" 或 "份额60%"
        share_pattern = re.findall(r'([^\s,，]{2,10})[^0-9]*?(\d+(?:\.\d+)?)\s*%', text)
        if len(share_pattern) >= 2:
            data_points = []
            for name, pct in share_pattern[:8]:
                try:
                    data_points.append(MetricDataPoint(label=name.strip(), value=float(pct)))
                except ValueError:
                    continue
            if len(data_points) >= 2:
                metrics.append(StructuredMetric(
                    metric_name="市场份额分布",
                    metric_type="market_share",
                    unit="%",
                    dimension=dimensions[-1] if dimensions else "",
                    data_points=data_points,
                    source="从文本中提取",
                    chart_type_hint="pie",
                ))

        return metrics

    def _rule_based_degradation(self, input_data: AnalyzerInput) -> AnalyzerOutput:
        logger.warning(f"LLM unreachable or failed for task '{input_data.task_id}'. Degrading to rule-based analysis.")
        insights = []
        summary_parts = []
        fallback_dim = input_data.dimensions[0] if input_data.dimensions else ""
        dims = input_data.dimensions if input_data.dimensions else ["综合分析"]

        for idx, item in enumerate(input_data.cleaned_items):
            summary_parts.append(item.title)
            full_text = "\n".join(item.content_chunks) if item.content_chunks else item.summary
            safe_summary = _sanitize_text(item.summary, 200)
            safe_content = _sanitize_text(full_text, 300)
            dim = dims[idx % len(dims)]
            analysis = safe_content if safe_content else f"Source '{item.title}' provides relevant information."
            insights.append(Insight(
                conclusion=safe_summary[:80] if safe_summary else f"Key finding from {item.title}",
                analysis=analysis,
                evidence=[item.source_uri],
                confidence=0.8,
                dimension=dim
            ))

        combined_summary = f"Analysis Summary for '{input_data.topic}': Found {len(input_data.cleaned_items)} relevant sources including {', '.join(summary_parts[:3])}. {len(input_data.cleaned_items)} key observations were extracted for further review."

        # 从清洗后的文本中提取结构化指标
        all_text = " ".join(
            " ".join(item.content_chunks) if item.content_chunks else item.summary
            for item in input_data.cleaned_items
        )
        structured_metrics = self._extract_metrics_from_text(all_text, input_data.dimensions)

        return AnalyzerOutput(
            task_id=input_data.task_id,
            success=True,
            summary=combined_summary,
            insights=insights,
            degraded=True,
            rag_results_count=0,
            rag_results=[],
            chart_plan=_build_chart_plan(insights),
            structured_metrics=structured_metrics,
        )

    async def execute(self, input_data: AnalyzerInput) -> AnalyzerOutput:
        await self._ensure_db_config()
        logger.info(f"AnalyzerAgent started for task_id: {input_data.task_id}, topic: '{input_data.topic}'")

        if not input_data.cleaned_items:
            logger.warning("No cleaned items provided for analysis.")
            return AnalyzerOutput(
                task_id=input_data.task_id,
                success=True,
                summary=f"No data available to analyze for topic '{input_data.topic}'.",
                insights=[],
                degraded=False
            )

        context_snippets = []
        rag_results: List[Dict[str, Any]] = []
        try:
            vectorstore = VectorStoreService()
            if vectorstore.collection_exists():
                embedding_service = EmbeddingService()
                rerank_service = RerankService()

                # 多关键词检索源:expanded_keywords 优先,topic 兜底
                if input_data.expanded_keywords:
                    query_list = list(input_data.expanded_keywords)
                    topic_included = False
                else:
                    query_list = [input_data.topic]
                    topic_included = True
                logger.info(
                    "RAG using %d query terms (expanded_keywords=%d, topic included=%s)",
                    len(query_list), len(input_data.expanded_keywords or []), topic_included
                )

                # 并行嵌入所有关键词
                all_embs = await asyncio.gather(
                    *[embedding_service.embed_texts_or_empty([q]) for q in query_list],
                    return_exceptions=True
                )

                # 对每条嵌入做搜索,合并 hits(按 text 去重,保留首次出现)
                seen_texts: set = set()
                all_hits: list = []
                for embs in all_embs:
                    if isinstance(embs, Exception) or not embs:
                        continue
                    emb = embs[0]
                    try:
                        hits = vectorstore.search(query_vector=emb, top_k=20)
                    except Exception as e:
                        logger.warning("vectorstore.search failed: %s", e)
                        continue
                    for h in hits or []:
                        text = h.get("text", "")
                        if text and text not in seen_texts:
                            seen_texts.add(text)
                            all_hits.append(h)

                if all_hits:
                    try:
                        reranked = await rerank_service.rerank(
                            query=input_data.topic,
                            documents=[h["text"] for h in all_hits]
                        )
                        context_snippets = reranked[:5]  # 原 top 3 → top 5
                        logger.info(
                            f"Retrieved {len(all_hits)} unique vector hits, reranked to {len(context_snippets)} context snippets for topic '{input_data.topic}'"
                        )
                    except Exception as e:
                        logger.warning("Rerank failed, using raw hits: %s", e)
                        context_snippets = all_hits[:5]
                else:
                    logger.info(f"No vector hits found for topic '{input_data.topic}'")
        except Exception as e:
            logger.warning(f"Failed to retrieve vector context for topic '{input_data.topic}': {e}")

        # 构建 RAG 结果摘要列表
        for snippet in context_snippets:
            text = snippet.get("text", "")
            rag_results.append({
                "title": snippet.get("report_id", "") or f"chunk_{snippet.get('id', '')}",
                "content_snippet": text[:200] if text else "",
                "relevance_score": snippet.get("score", 0.0),
            })

        prompt = self._build_prompt(input_data.topic, input_data.cleaned_items, input_data.dimensions, context_snippets if context_snippets else None)
        try:
            llm_result = await self._call_llm(prompt)
            summary = llm_result.get("summary", f"Analysis summary for {input_data.topic}")
            raw_insights = llm_result.get("insights", [])

            validated_insights = []
            valid_uris = {item.source_uri for item in input_data.cleaned_items}
            valid_dims = set(input_data.dimensions)

            for ri in raw_insights:
                conclusion = ri.get("conclusion", "")
                analysis = ri.get("analysis", "")
                evidence = ri.get("evidence", [])
                confidence = float(ri.get("confidence", 0.8))
                dimension = ri.get("dimension", ri.get("category", ""))

                if dimension and dimension not in valid_dims and valid_dims:
                    dim_lower = dimension.strip().lower()
                    for vd in valid_dims:
                        if vd.lower() == dim_lower or vd.lower().startswith(dim_lower[:4]) or dim_lower.startswith(vd.lower()[:4]):
                            dimension = vd
                            break
                    else:
                        dimension = list(valid_dims)[0]

                clean_evidence = [e for e in evidence if e in valid_uris]
                if not clean_evidence and valid_uris:
                    clean_evidence = [list(valid_uris)[0]]

                validated_insights.append(Insight(
                    conclusion=conclusion,
                    analysis=analysis,
                    evidence=clean_evidence,
                    confidence=max(0.0, min(1.0, confidence)),
                    dimension=dimension
                ))

            # 解析结构化指标
            raw_metrics = llm_result.get("structured_metrics", [])
            structured_metrics = self._parse_structured_metrics(raw_metrics)
            logger.info(
                f"Extracted {len(structured_metrics)} structured metrics from LLM for task '{input_data.task_id}'"
            )

            return AnalyzerOutput(
                task_id=input_data.task_id,
                success=True,
                summary=summary,
                insights=validated_insights,
                rag_results_count=len(rag_results),
                rag_results=rag_results,
                chart_plan=_build_chart_plan(validated_insights),
                structured_metrics=structured_metrics,
            )
        except Exception as e:
            logger.error(f"AnalyzerAgent LLM execution failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            return self._rule_based_degradation(input_data)
