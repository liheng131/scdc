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
import re
import traceback
from typing import List, Dict, Any, Tuple, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.schemas.agent import ReporterInput, ReporterOutput, ReportSection, Insight, DEFAULT_DIMENSIONS
from app.core.config import settings
from app.core.runtime_config import rumtime_config
from app.services.report_image import ReportImageService

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
        self.image_service = ReportImageService()

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
        # 空 dimensions 降级到 schema 默认值（DimensionGenerator 失败 / Orchestrator 未注入时）
        dims = list(dimensions) if dimensions else list(DEFAULT_DIMENSIONS)
        if not dimensions:
            logger.warning("Reporter degraded to default dimensions (none provided)")

        dim_sections: Dict[str, List[str]] = {d: [] for d in dims}
        for idx, ins in enumerate(insights, 1):
            dim = ins.dimension
            if dim not in dim_sections:
                dim = dims[0] if dims else ""
            dim_sections.setdefault(dim, []).append(
                f"  - {ins.conclusion} (置信度: {ins.confidence:.0%})\n"
                f"    分析: {ins.analysis}\n"
            )

        dim_blocks = []
        for dim in dims:
            entries = dim_sections.get(dim, [])
            if entries:
                dim_blocks.append(f"## {dim}\n{''.join(entries)}")
            else:
                dim_blocks.append(f"## {dim}\n  (暂无足够数据支撑该维度分析，请基于现有材料合理推断)\n")

        dim_text = "\n".join(dim_blocks)
        dim_outline = "\n".join(f"{i+1}. {d}" for i, d in enumerate(dims))
        # 用于在 prompt 中显式列出可用的 dimension 标签(供 [CHART: type|dimension] 引用)
        dim_slots_str = ", ".join(f"\"{d}\"" for d in dims)

        # 动态维度章节模板（按 dims 数量循环生成 LLM 章节指令）
        dim_chapter_blocks = []
        for i, dim in enumerate(dims, 1):
            dim_chapter_blocks.append(
                f"\n## {dim}\n"
                f"Write 2-4 paragraphs of substantive analysis for the '{dim}' dimension. "
                f"Integrate the corresponding insights naturally - do NOT just list them. "
                f"Include specific evidence, data points, and company references where available.\n"
                f"\n"
                f"**MANDATORY**: 在本章节末尾,你必须严格按照以下格式输出该章节的关键可量化数据点(用于生成统计图):\n"
                f"**数据点**:\n"
                f"- <指标名1>：<数值1><单位1>  (例: 2024年市场规模：1200亿元)\n"
                f"- <指标名2>：<数值2><单位2>  (例: 国产化率：35%)\n"
                f"- <指标名3>：<数值3><单位3>  (例: CR3头部集中度：65%)\n"
                f"\n"
                f"要求: 至少 3 个数据点,数据必须来自报告内容或可信分析,**严禁编造不存在的数字**。\n"
                f"如果确实没有可量化数据,请明确输出:**数据点**:无\n"
            )
        dim_chapters_text = "\n".join(dim_chapter_blocks)

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

The report must contain exactly {len(dims)} dynamic dimension chapters, one per dimension listed above. For each chapter:{dim_chapters_text}

## ⚠️ 跨维度风险与挑战
Write 2-3 paragraphs synthesizing risks that span multiple dimensions. Cover probability and impact.

## 💡 综合战略建议
Write 3-5 actionable, specific recommendations. Each as a bullet with 2-3 sentences of rationale.

## 🔗 数据来源说明
Briefly note data sources. Do NOT list individual URLs - the system will append those.

== IMAGE-TEXT COMBINATION (图文结合) REQUIREMENTS ==
- 每个分析章节应至少引用一个图表，使用 [CHART: type|dimension] 标记，如 [CHART: bar|宏观经济环境]
- 避免连续超过 300 字不包含图表引用
- chart_type 可选: bar(柱状图), line(折线图), pie(饼图), table(表格), matrix(矩阵), flow(流程图)
- dimension 必须是 {dim_slots_str} 之一
- 在需要展示数据对比的位置插入 [CHART: bar|<维度名>],在需要展示趋势的位置插入 [CHART: line|<维度名>],在需要展示占比/分布的位置插入 [CHART: pie|<维度名>]
- 标记应该嵌入到正文中,而不是单独成段,例如: "2024年市场规模达到1200亿元,同比增长15% [CHART: bar|宏观经济环境]"

== STYLE GUIDELINES ==
- Professional, boardroom-ready Chinese prose
- Data-driven: cite specific facts/numbers whenever possible
- Balanced: acknowledge uncertainty
- Actionable: every section should help decision-making
- Total: 1500-3000 Chinese characters
- Use ## headings, **bold**, bullet lists, > blockquotes
- 关键洞察用 > blockquote 引用格式包裹
- 各章节之间用 --- 分隔线"""

        return prompt

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)),
        reraise=True,
    )
    async def _call_llm(self, prompt: str, timeout: int = 120) -> str:
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

    # 正则:匹配 LLM 输出的 [CHART: type|dimension] 标记
    # type 允许: bar/line/pie/table/matrix/flow/comparison 等
    # dimension 允许中文/英文/数字,首尾空白会 strip
    _CHART_MARKER_RE = re.compile(
        r'\[\s*CHART\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*([^\]]+?)\s*\]'
    )

    def _build_chart_config_for_marker(
        self,
        chart_type: str,
        dimension: str,
        topic: str,
        insights: List[Insight],
    ) -> Dict[str, Any]:
        """
        根据 [CHART: type|dimension] 标记生成实际的 ECharts 图表配置

        Args:
            chart_type: 图表类型 (bar/line/pie/table/matrix/flow/comparison 等)
            dimension: 所属分析维度
            topic: 报告主题
            insights: 报告所有 insights(用于从 dimension 维度抽取数据)

        Returns:
            ECharts 配置 dict,可被前端 ECharts 渲染
        """
        chart_type_lower = (chart_type or "bar").strip().lower()
        dimension_clean = (dimension or "综合分析").strip()
        title = f"{dimension_clean} - {chart_type_lower} 图表"

        # 收集该维度下的所有 insight
        dim_insights = [
            ins for ins in insights
            if (ins.dimension or "").strip() == dimension_clean
        ]
        if not dim_insights:
            # 模糊匹配:维度包含关系
            for ins in insights:
                if dimension_clean and dimension_clean in (ins.dimension or ""):
                    dim_insights.append(ins)

        # 默认以 insight 数量与平均置信度作为数据源
        if chart_type_lower == "bar" or chart_type_lower == "comparison":
            labels = [ins.conclusion[:30] for ins in dim_insights] or [dimension_clean]
            values = [round(ins.confidence, 2) for ins in dim_insights] or [0.8]
            return {
                "title": {"text": title, "left": "center"},
                "tooltip": {"trigger": "axis"},
                "xAxis": {
                    "type": "category",
                    "data": labels,
                    "axisLabel": {"rotate": 20, "interval": 0},
                },
                "yAxis": {"type": "value", "name": "置信度", "min": 0, "max": 1},
                "series": [
                    {
                        "type": "bar",
                        "data": values,
                        "itemStyle": {"color": "#5470c6"},
                        "label": {"show": True, "position": "top"},
                    }
                ],
            }
        elif chart_type_lower == "line":
            labels = [ins.conclusion[:20] for ins in dim_insights] or [dimension_clean]
            values = [round(ins.confidence, 2) for ins in dim_insights] or [0.8]
            return {
                "title": {"text": title, "left": "center"},
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 20}},
                "yAxis": {"type": "value", "name": "置信度", "min": 0, "max": 1},
                "series": [
                    {
                        "type": "line",
                        "data": values,
                        "smooth": True,
                        "itemStyle": {"color": "#91cc75"},
                        "areaStyle": {"opacity": 0.3},
                    }
                ],
            }
        elif chart_type_lower == "pie":
            data = [
                {
                    "name": (ins.conclusion[:20] or f"洞察{i+1}"),
                    "value": round(max(ins.confidence, 0.1), 2),
                }
                for i, ins in enumerate(dim_insights)
            ] or [{"name": dimension_clean, "value": 1.0}]
            return {
                "title": {"text": title, "left": "center"},
                "tooltip": {"trigger": "item"},
                "legend": {"orient": "vertical", "left": "left"},
                "series": [
                    {
                        "name": "洞察占比",
                        "type": "pie",
                        "radius": "55%",
                        "center": ["50%", "60%"],
                        "data": data,
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
        elif chart_type_lower == "table":
            rows = [
                [ins.conclusion[:30], f"{ins.confidence:.0%}", len(ins.evidence)]
                for ins in dim_insights
            ] or [[dimension_clean, "80%", 0]]
            return {
                "title": {"text": title, "left": "center"},
                "type": "table",
                "headers": ["结论", "置信度", "证据数"],
                "rows": rows,
            }
        elif chart_type_lower == "matrix":
            # 矩阵/雷达图:按置信度分布在四个象限
            indicators = [
                {"name": ins.conclusion[:20] or f"洞察{i+1}", "max": 1.0}
                for i, ins in enumerate(dim_insights)
            ] or [{"name": dimension_clean, "max": 1.0}]
            values = [round(ins.confidence, 2) for ins in dim_insights] or [0.8]
            return {
                "title": {"text": title, "left": "center"},
                "tooltip": {},
                "radar": {"indicator": indicators},
                "series": [
                    {
                        "type": "radar",
                        "data": [
                            {
                                "value": values,
                                "name": dimension_clean,
                                "areaStyle": {"opacity": 0.3},
                            }
                        ],
                    }
                ],
            }
        elif chart_type_lower == "flow":
            # 流程图:以 insight 顺序构造简易关系
            nodes = [{"name": dimension_clean}]
            links = []
            for i, ins in enumerate(dim_insights):
                node_name = ins.conclusion[:20] or f"洞察{i+1}"
                nodes.append({"name": node_name})
                links.append({"source": dimension_clean, "target": node_name})
            return {
                "title": {"text": title, "left": "center"},
                "type": "flow",
                "nodes": nodes,
                "links": links,
            }
        else:
            # 未知类型,降级为柱状图
            return self._build_chart_config_for_marker(
                "bar", dimension, topic, insights
            )

    def inject_chart_references(
        self,
        markdown_report: str,
        topic: str,
        insights: List[Insight],
        dimensions: Optional[List[str]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        后处理 LLM 生成的报告,把文中 [CHART: type|dimension] 标记替换为实际图表配置。

        处理策略:
        1. 扫描报告中所有形如 ``[CHART: bar|宏观经济环境]`` 的标记
        2. 对每个标记:
           - 解析 chart_type 与 dimension
           - 调用 ``_build_chart_config_for_marker`` 生成 ECharts 配置
           - 同时用 ``_render_chart_to_base64`` 生成 PNG base64(降级显示用)
           - 把标记替换为 ``<!-- chart: {index} -->`` 注释 + markdown 引用
        3. 在文末追加 ``## 📊 图表清单`` 章节,列出所有图表
        4. 自动去除未识别的 / 重复的标记(降级)
        5. 保证 300 字内必有图表引用:在文末若仍有 300 字以上无图表的段落,补一个默认图表

        Args:
            markdown_report: LLM 生成的 markdown 报告原文
            topic: 报告主题
            insights: 报告所有 insights
            dimensions: 报告所有维度列表(可选,用于维度校验)

        Returns:
            (处理后的 markdown 报告, 图表配置列表)
        """
        if not markdown_report:
            return markdown_report, []

        # 1) 抽取所有 [CHART: type|dimension] 标记
        matches = list(self._CHART_MARKER_RE.finditer(markdown_report))
        if not matches:
            # 没有标记时,直接返回原报告,避免破坏既有内容
            return markdown_report, []

        # 2) 去重 + 维度校验
        seen: set = set()
        unique_markers: List[Tuple[str, str]] = []  # (chart_type, dimension)
        valid_dim_set = set(dimensions or [])
        for m in matches:
            chart_type = m.group(1).strip()
            dimension = m.group(2).strip()
            if valid_dim_set and dimension not in valid_dim_set:
                # 未知 dimension 时,尝试做一次模糊匹配
                matched_dim = None
                for vd in valid_dim_set:
                    if vd in dimension or dimension in vd:
                        matched_dim = vd
                        break
                if not matched_dim:
                    # 跳过无法识别的维度
                    continue
                dimension = matched_dim
            key = (chart_type.lower(), dimension)
            if key in seen:
                continue
            seen.add(key)
            unique_markers.append((chart_type, dimension))

        if not unique_markers:
            return markdown_report, []

        # 3) 顺序处理:从后往前替换,避免 index 错位
        new_md = markdown_report
        chart_configs: List[Dict[str, Any]] = []
        chart_titles: List[str] = []
        rendered_images: List[Dict[str, str]] = []

        # 重新从后往前扫描并替换
        for idx in range(len(matches) - 1, -1, -1):
            m = matches[idx]
            chart_type_raw = m.group(1).strip()
            dimension_raw = m.group(2).strip()
            if valid_dim_set and dimension_raw not in valid_dim_set:
                ok = False
                for vd in valid_dim_set:
                    if vd in dimension_raw or dimension_raw in vd:
                        dimension_raw = vd
                        ok = True
                        break
                if not ok:
                    # 移除该标记(空替换)
                    new_md = new_md[: m.start()] + new_md[m.end():]
                    continue

            # 查找在 unique_markers 中的索引(同 type+dim 只生成一次)
            try:
                real_idx = next(
                    i for i, (ct, d) in enumerate(unique_markers)
                    if ct.lower() == chart_type_raw.lower() and d == dimension_raw
                )
            except StopIteration:
                new_md = new_md[: m.start()] + new_md[m.end():]
                continue

            # 第一次遇到此 marker 时生成图表配置
            # 仅在 chart_configs 长度尚未达到 real_idx+1 时生成
            # (因为我们是从后往前遍历,可能先遇到 real_idx=1 后遇到 real_idx=0)
            if real_idx >= len(chart_configs) or chart_configs[real_idx].get("type") != chart_type_raw.lower() or chart_configs[real_idx].get("dimension") != dimension_raw:
                cfg = self._build_chart_config_for_marker(
                    chart_type_raw, dimension_raw, topic, insights
                )
                # 在 unique_markers 的真实位置插入
                # 调整 chart_configs 列表以保持顺序
                while len(chart_configs) <= real_idx:
                    chart_configs.append({})
                    chart_titles.append("")
                chart_configs[real_idx] = cfg
                chart_titles[real_idx] = cfg.get("title", {}).get("text", f"图表 {real_idx+1}")

            # 替换为可读标记,前端可识别
            replacement = f"[图表: {chart_titles[real_idx]}](#chart-{real_idx+1})"
            new_md = new_md[: m.start()] + replacement + new_md[m.end():]

        # 4) 过滤空配置
        chart_configs = [c for c in chart_configs if c]
        chart_titles = [t for t in chart_titles if t]

        # 5) 在文末追加图表清单
        if chart_titles:
            chart_list_md = "\n\n---\n\n## 📊 图表清单 (Chart Index)\n\n"
            for i, title in enumerate(chart_titles, 1):
                chart_list_md += f"- **图表 {i}** <a id=\"chart-{i}\"></a>: {title}\n"
                chart_list_md += f"  - 类型: {chart_configs[i-1].get('type', 'bar')}\n"
                chart_list_md += f"  - 配置: `chart_configs[{i-1}]`\n"
            new_md = new_md + chart_list_md

        # 6) 300 字不包含图表引用的兜底(用最终图引用计数)
        # 计算最长的无引用段(粗略)
        try:
            # 简单地按段落/换行分割
            segments = re.split(r'(\n\n+)', new_md)
            current_no_chart_len = 0
            patched_segments: List[str] = []
            for seg in segments:
                if not seg:
                    continue
                if "[图表:" in seg:
                    current_no_chart_len = 0
                    patched_segments.append(seg)
                    continue
                # 段内如果出现 [图表: 即重置
                seg_no_chart = re.sub(r'\[图表:[^\]]+\]\([^)]+\)', '', seg)
                if len(seg_no_chart) > 300 and current_no_chart_len + len(seg_no_chart) > 300:
                    # 在段尾追加一个默认图表引用(选第一个 chart_config)
                    if chart_configs:
                        fallback = chart_configs[0]
                        title = chart_titles[0] if chart_titles else "图表"
                        idx = 1
                        seg = seg.rstrip() + f" [图表: {title}](#chart-{idx})"
                    current_no_chart_len = 0
                else:
                    current_no_chart_len += len(seg_no_chart)
                patched_segments.append(seg)
            if patched_segments:
                new_md = "".join(patched_segments)
        except Exception as e:
            logger.debug("inject_chart_references: 300-char fallback skipped: %s", e)

        return new_md, chart_configs

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

    async def _generate_dimension_illustrations(
        self,
        topic: str,
        insights: List[Insight],
        dimensions: List[str],
        data_points_by_section: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        为每个分析维度生成配图

        数据真实性策略:
        1. **优先用 LLM 提供的数据点**（从 markdown 中解析的 **数据点** 块）画统计图
        2. 如果 LLM 没有给出数据点 → AI 图片生成（ComfyUI）
        3. AI 失败 → 用 LLM 数据点或 sample data 画 matplotlib 统计图
        4. matplotlib 失败 → 关键词卡片（无虚假数字）
        5. 关键词卡片失败 → 占位图

        Args:
            topic: 报告主题
            insights: 分析洞察列表
            dimensions: 分析维度列表
            data_points_by_section: LLM 在报告中显式给出的数据点,
                格式: {section_name: [{"label": str, "value": float, "unit": str}, ...]}

        Returns:
            配图数据列表，格式: [{"section": str, "title": str, "base64": str, "position": int}]
        """
        if not insights or not dimensions:
            return []

        data_points_by_section = data_points_by_section or {}
        illustrations = []
        position_counter = 1

        # 按维度分组 insights
        dim_groups: Dict[str, List[Insight]] = {}
        for insight in insights:
            dim = insight.dimension or "综合分析"
            dim_groups.setdefault(dim, []).append(insight)

        # 只为存在的维度生成配图
        target_dimensions = [d for d in dimensions if d in dim_groups]
        if not target_dimensions:
            target_dimensions = list(dim_groups.keys())[:len(dimensions)]

        logger.info(f"Generating illustrations for {len(target_dimensions)} dimensions")

        # 记录哪些维度成功生成了配图
        successful_dimensions = set()

        for dim in target_dimensions:
            dim_insights = dim_groups.get(dim, [])
            if not dim_insights:
                continue

            # 构建维度内容摘要
            content_summary = f"{dim}维度分析：\n"
            for ins in dim_insights[:3]:  # 取前 3 个 insights
                content_summary += f"- {ins.conclusion}\n"
                if ins.analysis:
                    content_summary += f"  {ins.analysis[:200]}\n"

            # 取出该维度的真实数据点（来自 LLM 报告）
            real_data_points = data_points_by_section.get(dim) or []

            # ─── 策略 1: 优先用真实数据点画统计图（保证数据真实性）───
            chart_generated = False
            if len(real_data_points) >= 3:
                try:
                    chart_result = self.image_service.generate_matplotlib_chart(
                        section_title=dim,
                        content="",  # 不再用正则抽取,直接传数据
                        data_points=real_data_points,  # 关键: 显式传入真实数据
                        chart_type=self._pick_chart_type(dim, real_data_points),
                    )
                    if chart_result:
                        illustrations.append({
                            "section": dim,
                            "title": chart_result["title"],
                            "base64": chart_result["base64"],
                            "position": position_counter,
                            "source": "real_data",
                        })
                        position_counter += 1
                        successful_dimensions.add(dim)
                        chart_generated = True
                        logger.info(
                            f"[REAL-DATA] Chart for '{dim}': "
                            f"{len(real_data_points)} data points from LLM"
                        )
                except Exception as e:
                    logger.warning(
                        f"Real data chart failed for '{dim}': "
                        f"{type(e).__name__}: {e}",
                        exc_info=True,
                    )

            # ─── 策略 2: AI 图片生成（ComfyUI）───
            ai_image = None
            if not chart_generated:
                try:
                    prompt = self.image_service._generate_section_prompt(dim, content_summary)
                    gen_result = await self.image_service.generate_section_image(prompt=prompt)

                    if gen_result and gen_result.get("image_url"):
                        ai_image = await self._download_image_as_base64(gen_result["image_url"])
                        if ai_image:
                            illustrations.append({
                                "section": dim,
                                "title": f"{dim} - AI 配图",
                                "base64": ai_image,
                                "position": position_counter,
                                "source": "ai",
                            })
                            position_counter += 1
                            successful_dimensions.add(dim)
                            chart_generated = True
                            logger.info(f"AI image generated for dimension '{dim}'")
                except Exception as e:
                    logger.warning(f"AI image generation failed for dimension '{dim}': {e}")

            # ─── 策略 3: matplotlib 降级（用 LLM 数据点或 insight 内容）───
            if not chart_generated:
                try:
                    # 优先用 LLM 真实数据点（1-2 个）画表格式图
                    # 退而求其次才用 insight 文本抽取
                    chart_result = None
                    if 1 <= len(real_data_points) <= 2:
                        # 1-2 个数据点 → 表格卡
                        chart_result = self.image_service.generate_table_chart(
                            section_title=dim,
                            data_points=real_data_points,
                        )
                        if chart_result:
                            logger.info(
                                f"[TABLE-CHART] '{dim}': {len(real_data_points)} points as table"
                            )
                    elif len(real_data_points) == 0:
                        # 无 LLM 数据点 → 关键词卡片（无虚假数字）
                        chart_result = self.image_service.generate_keyword_card(
                            section_title=dim,
                            content=content_summary,
                        )
                        if chart_result:
                            logger.info(f"[KEYWORD-CARD] '{dim}': no real data, using keyword card")

                    if chart_result:
                        illustrations.append({
                            "section": dim,
                            "title": chart_result["title"],
                            "base64": chart_result["base64"],
                            "position": position_counter,
                            "source": chart_result.get("source", "fallback"),
                        })
                        position_counter += 1
                        successful_dimensions.add(dim)
                        chart_generated = True
                except Exception as e:
                    logger.warning(
                        f"Fallback chart failed for '{dim}': "
                        f"{type(e).__name__}: {e}",
                        exc_info=True,
                    )

            # 限制每个维度最多 2 张图
            if position_counter > len(target_dimensions) * 2:
                break

        # 策略 4: 为没有成功生成配图的维度生成占位图（最终兜底）
        failed_dimensions = [d for d in target_dimensions if d not in successful_dimensions]
        if failed_dimensions:
            logger.info(f"Generating placeholder illustrations for {len(failed_dimensions)} failed dimensions")
            placeholder_illustrations = self._generate_placeholder_illustrations(failed_dimensions)
            for placeholder in placeholder_illustrations:
                placeholder["position"] = position_counter
                position_counter += 1
                illustrations.append(placeholder)

        logger.info(f"Generated {len(illustrations)} illustrations total")
        return illustrations

    def _pick_chart_type(self, dim: str, data_points: List[Dict[str, Any]]) -> str:
        """根据维度名和数据点数量选择最合适的图表类型"""
        title_lower = (dim or "").lower()

        # 趋势/预测类 → 折线图
        if any(kw in title_lower for kw in ["趋势", "预测", "走势", "展望"]):
            return "line"
        # 占比/份额/分布类 → 饼图
        if any(kw in title_lower for kw in ["占比", "份额", "结构", "构成", "分布"]):
            return "pie"
        # 竞争/对比类 → 柱状图
        if any(kw in title_lower for kw in ["竞争", "对比", "排名", "Top"]):
            return "bar"
        # 雷达/多维评估
        if any(kw in title_lower for kw in ["能力", "评估", "对比", "画像"]):
            if 3 <= len(data_points) <= 8:
                return "radar"
        # 数据点很多 → 柱状图
        if len(data_points) > 4:
            return "bar"
        return "bar"

    def _extract_data_points_from_markdown(
        self,
        markdown: str,
        dimensions: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        从 LLM 报告的 markdown 中提取每个章节的"**数据点**"块

        LLM 在每个维度章节末尾被要求输出格式:
        **数据点**:
        - 指标名：数值单位
        - 指标名：数值单位

        Returns:
            {section_name: [{"label": str, "value": float, "unit": str}, ...]}
        """
        result: Dict[str, List[Dict[str, Any]]] = {}
        if not markdown:
            return result

        # 拆分章节
        sections = re.split(r'\n(?=## )', markdown)
        for section_text in sections:
            # 提取章节标题
            title_match = re.match(r'##\s+(.+)', section_text.strip())
            if not title_match:
                continue
            section_title = title_match.group(1).strip()

            # 模糊匹配到 dimensions
            matched_dim = None
            for dim in dimensions:
                if self._match_section_heading(section_title, dim):
                    matched_dim = dim
                    break
            if not matched_dim:
                continue

            # 查找 **数据点** 块
            # 支持 "**数据点**:" "**数据点**：" "数据点:" 等
            dp_pattern = re.compile(
                r'\*?\*?数据点\*?\*?\s*[：:]\s*\n((?:[-•·]\s*.+\n?)+)',
                re.MULTILINE,
            )
            # 也支持单行格式 "**数据点**：无" / "**数据点**:无"
            none_pattern = re.compile(r'\*?\*?数据点\*?\*?\s*[：:]\s*无')

            if none_pattern.search(section_text):
                result[matched_dim] = []
                logger.debug(f"[DATA-POINTS] '{matched_dim}': LLM declared no data")
                continue

            dp_match = dp_pattern.search(section_text)
            if not dp_match:
                continue

            data_lines = dp_match.group(1).strip().split('\n')
            points = []
            for line in data_lines:
                line = line.strip().lstrip('-•·').strip()
                if not line:
                    continue
                # 解析 "指标名：数值单位" 或 "指标名: 数值 单位"
                # 数值支持负数（如 PPI -2.1%）
                m = re.match(
                    r'^(.+?)\s*[：:]\s*(-?\d+(?:\.\d+)?)\s*(.*)$',
                    line,
                )
                if m:
                    label = m.group(1).strip()
                    try:
                        value = float(m.group(2).strip())
                    except ValueError:
                        continue
                    unit = m.group(3).strip()
                    if label and len(label) <= 30:
                        points.append({
                            "label": label,
                            "value": value,
                            "unit": unit,
                        })
                    if len(points) >= 8:  # 限制最多 8 个
                        break

            if points:
                result[matched_dim] = points
                logger.info(
                    f"[DATA-POINTS] '{matched_dim}': extracted "
                    f"{len(points)} real data points from LLM"
                )

        return result

    async def _download_image_as_base64(self, image_url: str) -> Optional[str]:
        """
        下载图片并转换为 base64 编码

        Args:
            image_url: 图片 URL

        Returns:
            base64 编码的图片字符串，失败返回 None
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                return base64.b64encode(resp.content).decode()
        except Exception as e:
            logger.error(f"Failed to download image from {image_url}: {e}")
            return None

    def _extract_numeric_content(self, insights: List[Insight]) -> str:
        """
        从 insights 中提取数值内容用于 matplotlib 图表

        Args:
            insights: 洞察列表

        Returns:
            包含数值数据的字符串
        """
        content_parts = []
        for ins in insights:
            # 添加结论和分析中的数字
            content_parts.append(ins.conclusion)
            if ins.analysis:
                content_parts.append(ins.analysis)
        return " ".join(content_parts)

    def _generate_placeholder_illustrations(
        self,
        dimensions: List[str],
    ) -> List[Dict[str, Any]]:
        """
        生成占位图配图（当 AI 和 matplotlib 图表生成均失败时的降级方案）

        为每个维度生成一张简单的占位图，包含维度名称和提示信息。
        不依赖中文字体，使用纯图形元素确保在任何环境下都能生成。

        Args:
            dimensions: 分析维度列表

        Returns:
            占位图数据列表，格式: [{"section": str, "title": str, "base64": str, "position": int}]
        """
        illustrations = []
        for position, dim in enumerate(dimensions, 1):
            try:
                fig, ax = plt.subplots(figsize=(8, 5))
                # 使用纯图形元素，不依赖中文字体
                # 绘制一个带边框的矩形作为占位符
                rect = plt.Rectangle((0.1, 0.2), 0.8, 0.6,
                                     fill=False, edgecolor='#999999',
                                     linewidth=2, linestyle='--')
                ax.add_patch(rect)
                # 在矩形中央绘制一个图片图标（三角形+矩形组合）
                ax.plot([0.45, 0.55, 0.5], [0.35, 0.35, 0.5],
                       color='#999999', linewidth=2)
                ax.plot([0.4, 0.6], [0.55, 0.55],
                       color='#999999', linewidth=2)
                ax.plot([0.4, 0.4, 0.6, 0.6], [0.55, 0.65, 0.65, 0.55],
                       color='#999999', linewidth=2)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
                ax.set_facecolor('#f5f5f5')
                fig.patch.set_facecolor('#f5f5f5')

                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
                plt.close(fig)
                buf.seek(0)
                b64 = base64.b64encode(buf.read()).decode()

                illustrations.append({
                    "section": dim,
                    "title": f"{dim} - 占位图",
                    "base64": b64,
                    "position": position,
                })
                logger.info(f"Placeholder illustration generated for dimension '{dim}'")
            except Exception as e:
                logger.warning(f"Failed to generate placeholder for dimension '{dim}': {e}")

        return illustrations

    def _match_section_heading(self, heading: str, section_name: str) -> bool:
        """判断 Markdown 章节标题是否与配图的 section 字段匹配。

        匹配规则：
        1. 完全相等（忽略首尾空白）
        2. 章节标题包含 section 名称（子串匹配，忽略大小写）
        3. section 名称包含章节标题（子串匹配，忽略大小写）
        """
        heading_clean = heading.strip()
        section_clean = section_name.strip()
        if not section_clean:
            return False
        if heading_clean == section_clean:
            return True
        if section_clean.lower() in heading_clean.lower():
            return True
        if heading_clean.lower() in section_clean.lower():
            return True
        return False

    def _embed_illustrations_in_markdown(
        self,
        markdown_report: str,
        illustrations: List[Dict[str, Any]]
    ) -> str:
        """
        在 Markdown 报告中嵌入配图引用

        在每个维度章节末尾插入配图，使用 base64 内嵌方式。
        使用模糊匹配（包含关系）来匹配章节标题，与 report.py 中的 _match_section 逻辑一致。

        Args:
            markdown_report: 原始 Markdown 报告
            illustrations: 配图数据列表

        Returns:
            嵌入配图后的 Markdown 报告
        """
        if not illustrations:
            return markdown_report

        modified_report = markdown_report

        for illust in illustrations:
            section = illust["section"]
            title = illust["title"]
            b64_data = illust["base64"]

            # 使用模糊匹配查找章节位置
            matched_heading = None
            for line in modified_report.split("\n"):
                line_stripped = line.strip()
                if line_stripped.startswith("## "):
                    heading_text = line_stripped[3:].strip()
                    if self._match_section_heading(heading_text, section):
                        matched_heading = heading_text
                        break

            if matched_heading:
                # 找到匹配章节的起始位置
                section_pattern = rf'^## {re.escape(matched_heading)}$'
                match = re.search(section_pattern, modified_report, re.MULTILINE)
                if match:
                    # 找到下一个 ## 标题的位置
                    next_section_match = re.search(r'^## ', modified_report[match.end():], re.MULTILINE)
                    if next_section_match:
                        insert_pos = match.end() + next_section_match.start()
                    else:
                        # 如果没有下一个章节，插入到文档末尾
                        insert_pos = len(modified_report)

                    # 插入配图
                    image_markdown = f"\n\n![{title}](data:image/png;base64,{b64_data})\n"
                    modified_report = (
                        modified_report[:insert_pos] +
                        image_markdown +
                        modified_report[insert_pos:]
                    )
                    logger.debug(f"Embedded illustration for section '{section}' (matched '{matched_heading}') at position {insert_pos}")
                else:
                    image_markdown = f"\n\n![{title}](data:image/png;base64,{b64_data})\n"
                    modified_report += image_markdown
                    logger.warning(f"Could not find heading '{matched_heading}' in report, appending illustration at end")
            else:
                # 如果找不到匹配的章节，追加到文档末尾
                image_markdown = f"\n\n![{title}](data:image/png;base64,{b64_data})\n"
                modified_report += image_markdown
                logger.warning(f"Section '{section}' not found in report (no matching ## heading), appending illustration at end")

        return modified_report

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
                llm_report = await self._call_llm(prompt)

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

                    # 后处理:把 [CHART: type|dimension] 标记替换为实际图表配置
                    # 保持向后兼容:若 LLM 未输出任何标记,函数会原样返回
                    try:
                        full_markdown, marker_chart_configs = self.inject_chart_references(
                            full_markdown,
                            topic=input_data.topic,
                            insights=insights,
                            dimensions=dimensions if dimensions else DEFAULT_DIMENSIONS,
                        )
                        if marker_chart_configs:
                            # 合并到 chart_configs,让前端可一次性拿到全部图表
                            chart_configs = list(chart_configs) + list(marker_chart_configs)
                            logger.info(
                                f"injected {len(marker_chart_configs)} chart references from markers"
                            )
                    except Exception as e:
                        logger.warning(f"inject_chart_references failed (falling back): {e}")

                    # 从 LLM 报告中提取真实数据点
                    data_points_by_section = self._extract_data_points_from_markdown(
                        full_markdown,
                        dimensions if dimensions else DEFAULT_DIMENSIONS,
                    )

                    # 生成维度配图
                    dimension_illustrations = []
                    try:
                        dimension_illustrations = await self._generate_dimension_illustrations(
                            topic=input_data.topic,
                            insights=insights,
                            dimensions=dimensions if dimensions else DEFAULT_DIMENSIONS,
                            data_points_by_section=data_points_by_section,
                        )
                        if dimension_illustrations:
                            full_markdown = self._embed_illustrations_in_markdown(
                                full_markdown, dimension_illustrations
                            )
                            logger.info(f"Embedded {len(dimension_illustrations)} illustrations in report")
                    except Exception as e:
                        logger.warning(f"Failed to generate dimension illustrations: {e}")

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
                        dimension_illustrations=dimension_illustrations,
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

        # 从模板报告中提取真实数据点（如果有）
        dimensions = input_data.dimensions if input_data.dimensions else DEFAULT_DIMENSIONS
        data_points_by_section = self._extract_data_points_from_markdown(
            full_markdown, dimensions
        )

        # 生成维度配图（模板报告路径）
        dimension_illustrations = []
        try:
            dimension_illustrations = await self._generate_dimension_illustrations(
                topic=input_data.topic,
                insights=insights,
                dimensions=dimensions,
                data_points_by_section=data_points_by_section,
            )
            if dimension_illustrations:
                full_markdown = self._embed_illustrations_in_markdown(
                    full_markdown, dimension_illustrations
                )
                logger.info(f"Embedded {len(dimension_illustrations)} illustrations in template report")
        except Exception as e:
            logger.warning(f"Failed to generate dimension illustrations for template report: {e}")

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
            dimension_illustrations=dimension_illustrations,
            degraded=True,
        )