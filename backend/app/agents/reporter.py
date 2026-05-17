import datetime
import logging
from typing import List, Dict, Any, Tuple
from app.schemas.agent import ReporterInput, ReporterOutput, ReportSection, Insight

logger = logging.getLogger(__name__)

class ReporterAgent:
    def __init__(self):
        self.category_names = {
            "trend": "📈 行业发展趋势 (Trends)",
            "competitor": "🛡️ 竞争格局与动态 (Competitors)",
            "opportunity": "💡 潜在商业机会 (Opportunities)",
            "risk": "⚠️ 市场风险预警 (Risks)",
            "general": "🔍 综合分析观察 (General Observations)"
        }

    def _build_evidence_map(self, insights: List[Insight]) -> Tuple[Dict[str, int], List[str]]:
        # Map each unique URI to a footnote index [^1], [^2], etc.
        evidence_map: Dict[str, int] = {}
        reference_list: List[str] = []
        idx = 1
        for insight in insights:
            for uri in insight.evidence:
                if uri not in evidence_map:
                    evidence_map[uri] = idx
                    reference_list.append(uri)
                    idx += 1
        return evidence_map, reference_list

    def _generate_chart_configs(self, topic: str, insights: List[Insight]) -> List[Dict[str, Any]]:
        # Generate an ECharts standard configuration based on insight category distribution
        cat_counts: Dict[str, int] = {}
        for insight in insights:
            cat = insight.category if insight.category in self.category_names else "general"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        chart_data = [{"name": self.category_names.get(k, k).split(" ")[1], "value": v} for k, v in cat_counts.items()]

        option = {
            "title": {
                "text": f"洞察维度分布 - {topic}",
                "left": "center"
            },
            "tooltip": {
                "trigger": "item"
            },
            "legend": {
                "orient": "vertical",
                "left": "left"
            },
            "series": [
                {
                    "name": "洞察数量",
                    "type": "pie",
                    "radius": "50%",
                    "data": chart_data,
                    "emphasis": {
                        "itemStyle": {
                            "shadowBlur": 10,
                            "shadowOffsetX": 0,
                            "shadowColor": "rgba(0, 0, 0, 0.5)"
                        }
                    }
                }
            ]
        }
        return [option]

    async def execute(self, input_data: ReporterInput) -> ReporterOutput:
        logger.info(f"ReporterAgent started for task '{input_data.task_id}', topic '{input_data.topic}'")

        ao = input_data.analyzer_output
        insights = ao.insights
        evidence_map, reference_list = self._build_evidence_map(insights)

        sections: List[ReportSection] = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Section 1: Title & Metadata
        header_md = f"# 深度市场洞察报告：{input_data.topic}\n\n" \
                    f"> **执行时间**: {now_str}  \n" \
                    f"> **数据来源**: 全网多渠道汇聚清洗  \n" \
                    f"> **分析引擎**: SCDC AI Agent System\n"
        sections.append(ReportSection(title="报告元数据", content=header_md))

        # Section 2: Executive Summary
        exec_md = f"## 📑 执行摘要 (Executive Summary)\n\n{ao.summary}\n"
        sections.append(ReportSection(title="执行摘要", content=exec_md))

        # Section 3: Categorized Insights
        categories_dict: Dict[str, List[Insight]] = {}
        for insight in insights:
            cat = insight.category if insight.category in self.category_names else "general"
            categories_dict.setdefault(cat, []).append(insight)

        insights_md_parts = ["## 🎯 核心分析与洞察 (Key Insights)\n"]
        for cat_key, cat_label in self.category_names.items():
            cat_insights = categories_dict.get(cat_key, [])
            if not cat_insights:
                continue
            
            insights_md_parts.append(f"### {cat_label}\n")
            for ci in cat_insights:
                # Append footnotes
                footnote_tags = "".join([f"[^{evidence_map[uri]}]" for uri in ci.evidence if uri in evidence_map])
                conf_badge = f" `置信度: {ci.confidence:.1%}`" if ci.confidence > 0 else ""
                insights_md_parts.append(f"- **{ci.conclusion}**{conf_badge} {footnote_tags}\n")
            insights_md_parts.append("\n")

        insights_md = "\n".join(insights_md_parts)
        sections.append(ReportSection(title="核心洞察", content=insights_md))

        # Section 4: References & Footnotes
        ref_parts = ["## 🔗 来源与证据追踪 (References)\n"]
        for idx, uri in enumerate(reference_list, 1):
            ref_parts.append(f"[^{idx}]: [{uri}]({uri})")
        
        ref_md = "\n".join(ref_parts) + "\n"
        sections.append(ReportSection(title="来源追溯", content=ref_md))

        # Combine Full Markdown
        full_markdown = "\n".join([sec.content for sec in sections])

        # Generate Chart Configs if requested
        chart_configs = self._generate_chart_configs(input_data.topic, insights) if input_data.include_charts and insights else []

        logger.info(f"ReporterAgent successfully generated report for '{input_data.task_id}' ({len(full_markdown)} chars)")
        return ReporterOutput(
            task_id=input_data.task_id,
            success=True,
            markdown_report=full_markdown,
            sections=sections,
            chart_configs=chart_configs
        )
