"""
ReporterAgent（报告生成 Agent）

职责：
- 接收 AnalyzerAgent 的结构化分析结果，调用 LLM 撰写完整的叙事性市场洞察报告
- LLM 不可用时自动降级为模板组装模式
- 生成 ECharts 饼图配置，展示洞察维度分布
"""

import base64
import datetime
import io
import json
import logging
import os
import traceback
from typing import List, Dict, Any, Tuple

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.schemas.agent import ReporterInput, ReporterOutput, ReportSection, Insight
from app.core.config import settings
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)

# Configure Chinese font support
# 覆盖 Windows / macOS / Linux 三个平台的中文字体路径
# 报告里的图表在以下任一路径命中即可正确渲染中文，避免方框乱码
_font_paths = [
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",         # 微软雅黑（首选）
    r"C:\Windows\Fonts\msyhbd.ttc",       # 微软雅黑 Bold
    r"C:\Windows\Fonts\simhei.ttf",        # 黑体
    r"C:\Windows\Fonts\simsun.ttc",        # 宋体
    r"C:\Windows\Fonts\Deng.ttf",          # 等线
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Songti.ttc",
    # Linux (Docker 容器内)
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
]
# 候选 sans-serif 名称（matplotlib 按顺序 fallback）
_sans_candidates = [
    "Microsoft YaHei",       # 微软雅黑
    "SimHei",                # 黑体
    "SimSun",                # 宋体
    "DengXian",              # 等线
    "PingFang SC",           # macOS 苹方
    "STHeiti",               # macOS 华文黑体
    "Songti SC",             # macOS 宋体
    "WenQuanYi Micro Hei",   # Linux 文泉驿微米黑
    "WenQuanYi Zen Hei",     # Linux 文泉驿正黑
    "Noto Sans CJK SC",      # Noto CJK
    "Noto Sans CJK",         # Noto CJK 通用名
    "DejaVu Sans",           # matplotlib 默认（兜底，必有）
]
_selected_font = None
for _fp in _font_paths:
    if os.path.exists(_fp):
        try:
            fm.fontManager.addfont(_fp)
            _selected_font = _fp
            logger.info("Registered Chinese font for matplotlib: %s", _fp)
        except Exception as _e:
            logger.warning("Failed to register font %s: %s", _fp, _e)
        break
if _selected_font:
    matplotlib.rcParams['font.sans-serif'] = _sans_candidates
    matplotlib.rcParams['axes.unicode_minus'] = False
else:
    logger.warning(
        "No Chinese font found in known paths. "
        "Charts may display garbled Chinese text (boxes □). "
        "Install fonts-wqy-microhei (Linux) or ensure C:\\Windows\\Fonts\\msyh.ttc exists (Windows)."
    )
del _font_paths, _fp, _sans_candidates, _selected_font


class ReporterAgent:
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

    def _build_report_prompt(
        self,
        topic: str,
        summary: str,
        insights: List[Insight],
        dimensions: List[str],
        source_contents: List[Dict[str, Any]] = None,
    ) -> str:
        dim_sections: Dict[str, List[str]] = {d: [] for d in dimensions}
        for idx, ins in enumerate(insights, 1):
            dim = ins.dimension
            if dim not in dim_sections:
                dim = dimensions[0] if dimensions else ""
            dim_sections.setdefault(dim, []).append(
                f"  - {ins.conclusion} (置信度: {ins.confidence:.0%})\n"
                f"    分析: {ins.analysis}\n"
            )

        dim_blocks = []
        for dim in dimensions:
            entries = dim_sections.get(dim, [])
            if entries:
                dim_blocks.append(f"## {dim}\n{''.join(entries)}")
            else:
                dim_blocks.append(f"## {dim}\n  (暂无足够数据支撑该维度分析，请基于现有材料合理推断)\n")

        dim_text = "\n".join(dim_blocks)
        dim_outline = "\n".join(f"{i+1}. {d}" for i, d in enumerate(dimensions))

        sources_section = ""
        if source_contents:
            source_parts = []
            for i, sc in enumerate(source_contents):
                source_parts.append(
                    f"--- Source #{i+1} ---\n"
                    f"Title: {sc.get('title', 'N/A')}\n"
                    f"URI: {sc.get('uri', 'N/A')}\n"
                    f"Content: {sc.get('content', '')[:2000]}\n"
                )
            sources_section = "\n== SOURCE MATERIALS FOR REFERENCE ==\n" + "\n".join(source_parts) + "\n"

        prompt = f"""You are a senior market intelligence analyst at McKinsey & Company with 20 years of experience. Write a professional, deep market insight report in Chinese.

The topic is: "{topic}"

Below is the structured analysis prepared by an AI research assistant, organized by analytical dimensions. Your job is to transform it into a polished, boardroom-ready report.

{sources_section}
== EXECUTIVE SUMMARY ==
{summary}

== INSIGHTS BY DIMENSION ==
{dim_text}

== REPORT STRUCTURE REQUIREMENTS ==

Write in Chinese. Follow this structure:

## 📑 执行摘要 (Executive Summary)
Write 3-4 paragraphs (250-400 words) synthesizing findings across ALL dimensions. Include key numbers, company names, and directional signals.

{dim_outline}

For each of the {len(dimensions)} dimensions above, write a dedicated chapter:
- Start with ## 标题, using the exact dimension name
- Write 2-4 paragraphs per dimension with substantive analysis
- Integrate the corresponding insights naturally - do NOT just list them
- Include specific evidence, data points, and company references where available

## ⚠️ 跨维度风险与挑战
Write 2-3 paragraphs synthesizing risks that span multiple dimensions. Cover probability and impact.

## 💡 综合战略建议
Write 3-5 actionable, specific recommendations. Each as a bullet with 2-3 sentences of rationale.

## 🔗 数据来源说明
Briefly note data sources. Do NOT list individual URLs - the system will append those.

== STYLE GUIDELINES ==
- Professional, boardroom-ready Chinese prose
- Data-driven: cite specific facts/numbers whenever possible
- Balanced: acknowledge uncertainty
- Actionable: every section should help decision-making
- Total: 1500-3000 Chinese characters
- Use ## headings, **bold**, bullet lists, > blockquotes"""

        return prompt

    @retry(
        stop=stop_after_attempt(1),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)),
        reraise=True,
    )
    async def _call_llm(self, prompt: str, timeout: int = 60) -> str:
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
                "stream": False,
                "options": {"temperature": rumtime_config.get("temperature")},
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.llm_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

            if self.llm_provider == "gpustack":
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                return data.get("response", "")

    def _build_evidence_map(self, insights: List[Insight]) -> Tuple[Dict[str, int], List[str]]:
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
        dim_counts: Dict[str, int] = {}
        dim_confidences: Dict[str, List[float]] = {}
        for insight in insights:
            dim = insight.dimension or "未分类"
            dim_counts[dim] = dim_counts.get(dim, 0) + 1
            dim_confidences.setdefault(dim, []).append(insight.confidence)

        chart_data = [{"name": k, "value": v} for k, v in dim_counts.items()]

        pie_option = {
            "title": {"text": f"分析维度分布 - {topic}", "left": "center"},
            "tooltip": {"trigger": "item"},
            "legend": {"orient": "vertical", "left": "left"},
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
                            "shadowColor": "rgba(0, 0, 0, 0.5)",
                        }
                    },
                }
            ],
        }

        dim_names = list(dim_counts.keys())
        avg_confidences = [
            sum(dim_confidences.get(d, [0])) / max(len(dim_confidences.get(d, [])), 1)
            for d in dim_names
        ]

        bar_option = {
            "title": {"text": f"各维度置信度分布 - {topic}", "left": "center"},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": dim_names, "axisLabel": {"rotate": 30}},
            "yAxis": {"type": "value", "name": "平均置信度", "min": 0, "max": 1},
            "series": [{"data": avg_confidences, "type": "bar", "itemStyle": {"color": "#5470c6"}}]
        }

        return [pie_option, bar_option]

    def _render_chart_to_base64(self, chart_configs: List[Dict]) -> List[Dict[str, str]]:
        images = []
        for cfg in chart_configs:
            title = cfg.get("title", {}).get("text", "Chart")
            fig, ax = plt.subplots(figsize=(8, 5))
            series_list = cfg.get("series", [])
            for series in series_list:
                if series.get("type") == "pie":
                    data_items = series.get("data", [])
                    labels = [d.get("name", "") for d in data_items]
                    values = [d.get("value", 0) for d in data_items]
                    if labels and values:
                        ax.pie(values, labels=labels, autopct='%1.1f%%')
                elif series.get("type") == "bar":
                    x_data = cfg.get("xAxis", {}).get("data", [])
                    y_data = series.get("data", [])
                    if x_data and y_data:
                        ax.bar(x_data, y_data)
                        ax.set_ylabel(cfg.get("yAxis", {}).get("name", ""))
            ax.set_title(title)
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
            images.append({"title": title, "base64": b64})
        return images

    def _build_template_report(
        self,
        topic: str,
        summary: str,
        insights: List[Insight],
        evidence_map: Dict[str, int],
        reference_list: List[str],
    ) -> str:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        header = (
            f"# 深度市场洞察报告：{topic}\n\n"
            f"> **执行时间**: {now_str}  \n"
            f"> **数据来源**: 全网多渠道汇聚清洗  \n"
            f"> **分析引擎**: SCDC AI Agent System  \n"
            f"> *注：LLM 报告生成服务暂不可用，以下为结构化数据输出*\n\n"
            f"---\n\n"
        )

        exec_section = f"## 📑 执行摘要 (Executive Summary)\n\n{summary}\n\n"

        dim_groups: Dict[str, List[Insight]] = {}
        for insight in insights:
            dim = insight.dimension or "综合分析"
            dim_groups.setdefault(dim, []).append(insight)

        insights_parts = ["## 🎯 维度分析 (Dimension Analysis)\n"]
        for dim_label, dim_insights in dim_groups.items():
            insights_parts.append(f"### {dim_label}\n")
            for ci in dim_insights:
                footnote_tags = "".join(
                    [f"[^{evidence_map[uri]}]" for uri in ci.evidence if uri in evidence_map]
                )
                conf_badge = f" `置信度: {ci.confidence:.1%}`" if ci.confidence > 0 else ""
                insights_parts.append(f"**{ci.conclusion}**{conf_badge}{footnote_tags}\n\n")
                if ci.analysis:
                    insights_parts.append(f"{ci.analysis}\n\n")
            insights_parts.append("\n")

        ref_parts = ["## 🔗 来源与证据追踪 (References)\n"]
        for idx, uri in enumerate(reference_list, 1):
            ref_parts.append(f"[^{idx}]: [{uri}]({uri})\n")

        return header + exec_section + "\n".join(insights_parts) + "\n".join(ref_parts)

    async def execute(self, input_data: ReporterInput) -> ReporterOutput:
        await self._ensure_db_config()
        logger.info(
            f"ReporterAgent started for task '{input_data.task_id}', topic '{input_data.topic}'"
        )

        ao = input_data.analyzer_output
        insights = ao.insights
        summary = ao.summary
        evidence_map, reference_list = self._build_evidence_map(insights)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chart_configs = (
            self._generate_chart_configs(input_data.topic, insights)
            if input_data.include_charts and insights
            else []
        )
        chart_images = self._render_chart_to_base64(chart_configs) if chart_configs else []

        sections: List[ReportSection] = []

        if insights:
            try:
                logger.info(f"ReporterAgent calling LLM for topic '{input_data.topic}'")
                dimensions = input_data.dimensions if input_data.dimensions else []
                prompt = self._build_report_prompt(
                    input_data.topic, summary, insights, dimensions,
                    source_contents=input_data.source_contents if input_data.source_contents else None,
                )
                llm_report = await self._call_llm(prompt, timeout=120)

                if llm_report and len(llm_report.strip()) > 100:
                    header_md = (
                        f"# 深度市场洞察报告：{input_data.topic}\n\n"
                        f"> **执行时间**: {now_str}  \n"
                        f"> **数据来源**: 全网多渠道汇聚清洗  \n"
                        f"> **分析引擎**: SCDC AI Agent System\n\n"
                        f"---\n\n"
                    )
                    ref_parts = ["\n\n## 🔗 来源与证据追踪 (References)\n"]
                    for idx, uri in enumerate(reference_list, 1):
                        ref_parts.append(f"[^{idx}]: [{uri}]({uri})\n")

                    full_markdown = header_md + llm_report.strip() + "\n".join(ref_parts)
                    if chart_images:
                        for ci in chart_images:
                            full_markdown += f"\n\n![{ci['title']}](data:image/png;base64,{ci['base64']})"
                    sections.append(ReportSection(title="完整报告", content=full_markdown))

                    logger.info(
                        f"ReporterAgent LLM report generated for '{input_data.task_id}' "
                        f"({len(full_markdown)} chars)"
                    )
                    return ReporterOutput(
                        task_id=input_data.task_id,
                        success=True,
                        markdown_report=full_markdown,
                        sections=sections,
                        chart_configs=chart_configs,
                        chart_images=chart_images,
                        degraded=False,
                    )
                else:
                    logger.warning(
                        f"LLM returned short/invalid report for '{input_data.task_id}', "
                        f"falling back to template"
                    )
            except Exception as e:
                logger.error(
                    f"ReporterAgent LLM call failed for '{input_data.task_id}': "
                    f"{type(e).__name__}: {e}. Falling back to template\n{traceback.format_exc()}"
                )

        full_markdown = self._build_template_report(
            input_data.topic, summary, insights, evidence_map, reference_list
        )
        if chart_images:
            for ci in chart_images:
                full_markdown += f"\n\n![{ci['title']}](data:image/png;base64,{ci['base64']})"
        sections.append(ReportSection(title="完整报告", content=full_markdown))

        logger.info(
            f"ReporterAgent template report generated for '{input_data.task_id}' "
            f"({len(full_markdown)} chars)"
        )
        return ReporterOutput(
            task_id=input_data.task_id,
            success=True,
            markdown_report=full_markdown,
            sections=sections,
            chart_configs=chart_configs,
            chart_images=chart_images,
            degraded=True,
        )