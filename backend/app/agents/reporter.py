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
from app.services.report_page_model import ReportPageModel, PageModel
from app.services.markdown_parser import MarkdownPageParser
from app.services.quality_validator import QualityValidator, ValidationResult

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

        prompt = f"""You are a senior market intelligence analyst at a top consulting firm. Output a PROFESSIONAL, DATA-RICH presentation deck in Chinese for html-ppt rendering. Your report will be read by senior executives.

Topic: "{topic}"

== ANALYSIS DATA ==
Executive Summary:
{summary}

Dimensions to cover: {', '.join(dims)}

Insights by dimension:
{dim_text}

Source materials (for fact-checking only):
{sources_section if sources_section else '(none)'}

== YOUR TASK ==
Follow the html-ppt design system rules below. Output ONLY a JSON array of slides in ```json ... ```.

{self._load_html_ppt_skill()}

== SLIDE STRUCTURE (12-24 slides, professional depth) ==
1. cover (1 slide)
2. toc (1 slide)
3-4. Per dimension (total 10-20 slides allocated across {len(dims)} dimensions):
   - Dimension section divider (1 slide)
   - Core analysis (2-3 content/bullets/two_column slides — deep, multi-paragraph)
   - Data visualization (1 kpi_grid or chart_bar/chart_pie slide — real numbers only)
   - Image page (1 image_hero or image_grid slide — suggest images for every dimension)
   - OPTIONAL: counter-analysis or competing viewpoint slide (1 slide)
5. thanks (1 slide)

Supported layouts: cover / toc / section / content / bullets / kpi_grid / two_column / three_column / table / stat / chart_bar / chart_line / chart_pie / image_hero / image_grid / thanks

JSON format (OUTPUT PURE JSON ONLY, NO Markdown):

```json
{{
  "theme": "corporate-clean",
  "pages": [
    {{
      "layout": "cover",
      "title": "报告主标题（精炼有力，包含关键词）",
      "kicker": "Market Insight Report",
      "text_blocks": [
        {{"text": "副标题 · 日期 · 团队名称", "is_lead": false}},
        {{"text": "核心发现一句话总结（50字以内，吸引眼球）", "is_lead": true}}
      ],
      "notes": "180-350字开场白：本次报告背景、核心主题、关键发现预览、阅读建议",
      "image_hints": ["抽象科技感/数据感背景图, 深色调"]
    }},
    {{
      "layout": "toc",
      "title": "报告目录",
      "text_blocks": [
        {{"text": "01 " + dims[0] if dims else "维度1", "emphasis": []}},
        {{"text": "02 " + dims[1] if len(dims) > 1 else "维度2", "emphasis": []}},
        {{"text": "03 " + dims[2] if len(dims) > 2 else "维度3", "emphasis": []}},
        {{"text": "04 总结与展望", "emphasis": []}}
      ],
      "notes": "180-350字：各章节内容简介、阅读路径建议"
    }},
    {{
      "layout": "section",
      "title": "01 / 维度名称",
      "kicker": "PART 1",
      "text_blocks": [
        {{"text": "本章核心发现一句话", "is_lead": true}}
      ],
      "notes": "180-350字：本章节关键问题、分析框架、预期收获"
    }},
    {{
      "layout": "content",
      "title": "具体分析标题（观点性、有信息量）",
      "kicker": "关键发现",
      "text_blocks": [
        {{"text": "第一段（300-500字）：详细分析核心趋势、市场规模、增长驱动因素，引用具体数字、厂商名称、政策文本。必须包含至少2个可核查的数据点。", "is_lead": false, "emphasis": ["关键词A", "关键词B"]}},
        {{"text": "第二段（300-500字）：行业竞争格局、技术路线分歧、区域分布、产业链变化。对比不同参与者的策略差异。", "is_lead": false, "emphasis": ["关键词C"]}},
        {{"text": "第三段（200-400字）：影响与展望。分析此趋势对产业链各环节的短期和长期影响，给出具体判断而非模糊预测。", "is_lead": false, "emphasis": []}}
      ],
      "source": "来源: 行家说, LED inside",
      "notes": "180-350字演讲稿：用口语化语言讲清楚本页核心观点，引导听众关注关键数据",
      "image_hints": ["行业趋势图表, 数据可视化, 深蓝科技风格"]
    }},
    {{
      "layout": "kpi_grid",
      "title": "关键数据指标",
      "kpi_metrics": [
        {{"label": "市场规模", "value": "4,500亿", "raw_value": 4500, "unit": "亿元", "change": "+42% YoY", "trend": "up"}},
        {{"label": "增长率", "value": "42%", "raw_value": 42, "unit": "%", "change": "+8pp vs上年", "trend": "up"}},
        {{"label": "CR3集中度", "value": "65%", "raw_value": 65, "unit": "%", "change": "+5pp", "trend": "up"}},
        {{"label": "国产化率", "value": "35%", "raw_value": 35, "unit": "%", "change": "+12pp", "trend": "up"}}
      ],
      "notes": "180-350字：逐一解读KPI含义、关联关系、异常值解释"
    }},
    {{
      "layout": "image_hero",
      "title": "相关图表与视觉材料",
      "text_blocks": [{{"text": "图表说明文字", "is_lead": false}}],
      "image_hints": ["产业链全景图, 市场占有率饼图, 科技信息图风格"],
      "notes": "180-350字"
    }},
    {{
      "layout": "thanks",
      "title": "Thank You",
      "text_blocks": [
        {{"text": "报告由SCDC AI Agent生成"}},
        {{"text": "关键结论回顾：1) ... 2) ... 3) ..."}}
      ],
      "notes": "180-350字结语：3-5条核心takeaway、下一步行动建议"
    }}
  ]
}}
```

== FINAL RULES (STRICT) ==
- Output ONLY ```json ... ``` block. NO Markdown, NO explanations before/after.
- Total 12-24 slides. Each dimension gets 3-5 slides (section + 2-3 content + kpi/chart + image).
  VARY layouts — never same layout on consecutive slides. Use at least 8 different layout types across the deck.
- Every slide MUST have "notes" (180-350 chars colloquial Chinese speaker script).
- KPI/chart data STRICTLY from analysis data above. Mark invented data with confidence caveat in notes.
- text_blocks: 200-500 chars each, 2-4 blocks per content slide. Write SUBSTANTIVE analysis paragraphs, not bullet-point fragments.
- "emphasis" array lists 1-3 key terms per text block to highlight in accent color.
- "image_hints": REQUIRED for content/kpi_grid/section/image_hero pages. Describe scene/style/mood (Chinese). At least 40% of all slides should have image_hints.
- "source": Include source citations ("来源: ...") in text_blocks or as separate field for data-heavy slides.
- Cover slide MUST have a lead text_block with the core finding hook.
- Thanks slide MUST recap 3-5 key takeaways.
- counter-analysis: For at least ONE dimension, include a slide examining competing viewpoints, risks, or counter-arguments (不呈现单一乐观叙事)."""
        return prompt

    @staticmethod
    def _load_html_ppt_skill() -> str:
        """动态加载 html-ppt SKILL.md，解耦设计规则与代码"""
        import os
        skill_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "html-ppt", "SKILL.md"
        )
        if not os.path.exists(skill_path):
            logger.warning("html-ppt SKILL.md not found at %s, using minimal rules", skill_path)
            return """== html-ppt MINIMAL RULES ==
- Output slides with layout types: cover/toc/section/content/kpi_grid/chart_bar/chart_pie/stat/thanks
- Every slide needs "notes" field (150-300 Chinese chars speaker script)
- VARY layouts across slides, never text-only slides
- KPI/chart data must come from analysis data, do not fabricate"""

        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                skill_content = f.read()

            # 提取核心配置段落（去掉不相关的安装/脚本部分）
            sections = []
            for line in skill_content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("## "):
                    section_name = stripped[3:]
                    # 只保留设计相关段落
                    if section_name in (
                        "When to use",
                        "What the skill gives you",
                        "design ideas",
                        "Design Ideas",
                        "For Each Slide",
                        "Typography",
                        "Spacing",
                        "Avoid (Common Mistakes)",
                        "Authoring rules (important)",
                        "Writing guide",
                        "色彩和字体",
                        "配色方案",
                        "Color Palettes",
                    ):
                        sections.append(f"<!-- {section_name} -->")
                    else:
                        sections.append(f"<!-- SKIP {section_name} -->")
                else:
                    sections.append(line)

            result = "\n".join(sections)

            # 截断过长内容（LLM token 限制），提升到 12000 以传递更丰富的设计规则
            if len(result) > 12000:
                result = result[:12000] + "\n\n<!-- SKILL.md truncated to 12000 chars -->"

            logger.info("Loaded html-ppt SKILL.md: %d chars", len(result))
            return "== html-ppt DESIGN SYSTEM (from SKILL.md) ==\n" + result
        except Exception as e:
            logger.warning("Failed to load html-ppt SKILL.md: %s", e)
            return """== html-ppt MINIMAL RULES ==
- Output slides as JSON with layouts: cover/toc/section/content/kpi_grid/chart_bar/chart_pie/stat/thanks
- Every slide needs "notes" (150-300 chars speaker script)
- VARY layouts, never text-only, KPI data from analysis only"""

    # ── JSON 提取正则 ──
    _JSON_BLOCK_RE = re.compile(r"```(?:json|JSON)?\s*(\{[\s\S]+?\})\s*```", re.MULTILINE)

    def _extract_pages_from_llm_response(
        self,
        llm_response: str,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], Optional[str]]:
        """
        从 LLM 原始响应中提取 PageModel 列表 + theme + notes_summary

        Returns:
            (pages, theme, notes_summary) — 任意字段解析失败时该项为 None
        """
        if not llm_response:
            return None, None, None

        # 1) 匹配 json 代码块
        json_text: Optional[str] = None
        m = self._JSON_BLOCK_RE.search(llm_response)
        if m:
            json_text = m.group(1)
        else:
            # 2) 兜底：尝试提取首段大括号 JSON（从第一个 { 到匹配的最后一个 }）
            try:
                start = llm_response.index("{")
                # 用栈式扫描定位匹配的大括号
                depth = 0
                end = -1
                for idx in range(start, len(llm_response)):
                    ch = llm_response[idx]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end = idx
                            break
                if end > start:
                    json_text = llm_response[start : end + 1]
            except ValueError:
                pass

        if not json_text:
            logger.debug("No JSON block found in LLM response for PageModel extraction")
            return None, None, None

        # 3) 解析 JSON
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.info(
                "Failed to parse PageModel JSON from LLM response: %s. "
                "Will fall back to MarkdownPageParser.",
                e,
            )
            return None, None, None

        if not isinstance(payload, dict):
            logger.info("LLM JSON payload is not a dict, falling back")
            return None, None, None

        pages = payload.get("pages")
        if not isinstance(pages, list) or not pages:
            logger.info("LLM JSON has no 'pages' list, falling back to MarkdownPageParser")
            return None, None, None

        theme = payload.get("theme")
        if not isinstance(theme, str) or not theme.strip():
            theme = None
        notes_summary = payload.get("notes_summary")
        if not isinstance(notes_summary, str):
            notes_summary = None

        # 4) 基本字段类型校验
        valid_layouts = {
            "cover", "toc", "section", "content", "bullets", "kpi_grid",
            "two_column", "three_column", "table", "image_hero", "image_grid",
            "stat", "thanks",
            "chart_bar", "chart_line", "chart_pie",
        }
        for idx, page in enumerate(pages):
            if not isinstance(page, dict):
                logger.info("Page %d is not a dict, dropping", idx)
                return None, None, None
            layout = page.get("layout", "content")
            if layout not in valid_layouts:
                page["layout"] = "content"  # 未知 layout 降级
            if not page.get("page_type"):
                page["page_type"] = "content"
            if not page.get("title"):
                page["title"] = f"第 {idx + 1} 页"
            if not isinstance(page.get("text_blocks"), list):
                page["text_blocks"] = []
            if not isinstance(page.get("image_blocks"), list):
                page["image_blocks"] = []
            if not isinstance(page.get("kpi_metrics"), list):
                page["kpi_metrics"] = []
            if not isinstance(page.get("chart_data"), dict):
                page["chart_data"] = None
            if not isinstance(page.get("image_hints"), list):
                page["image_hints"] = []
            if not isinstance(page.get("animations"), list):
                page["animations"] = ["fade-up"]  # 兜底加一个动效
            if not page.get("notes"):
                page["notes"] = page.get("title", "")

        logger.info(
            "ReporterAgent extracted %d structured pages from LLM response (theme=%s, notes_summary=%d chars)",
            len(pages), theme or "(default)", len(notes_summary or ""),
        )
        return pages, theme, notes_summary

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

        # 5) 300 字不包含图表引用的兜底
        # 检查段落是否已包含图表引用（[图表:...] 或 base64 内嵌图片 ![...](data:image/...)）
        try:
            segments = re.split(r'(\n\n+)', new_md)
            current_no_chart_len = 0
            patched_segments: List[str] = []
            for seg in segments:
                if not seg:
                    continue
                # 检查是否已有图表引用：[图表:...] 或 base64 内嵌图片
                has_chart_ref = bool(re.search(r'\[图表:[^\]]+\]\([^)]+\)', seg))
                has_inline_img = bool(re.search(r'!\[[^\]]*\]\(data:image/', seg))
                if has_chart_ref or has_inline_img:
                    current_no_chart_len = 0
                    patched_segments.append(seg)
                    continue
                # 移除图表引用后计算纯文本长度
                seg_no_chart = re.sub(r'\[图表:[^\]]+\]\([^)]+\)', '', seg)
                seg_no_chart = re.sub(r'!\[[^\]]*\]\(data:image/[^)]+\)', '', seg_no_chart)
                if len(seg_no_chart) > 300 and current_no_chart_len + len(seg_no_chart) > 300:
                    # 在段尾追加一个默认图表引用(选第一个 chart_config)
                    if chart_configs:
                        title = chart_titles[0] if chart_titles else "图表"
                        seg = seg.rstrip() + f" [图表: {title}](#chart-1)"
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
        structured_metrics: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        为每个分析维度生成配图

        数据真实性策略:
        1. **优先用 AnalyzerAgent 提取的结构化指标** (structured_metrics) 画统计图
        2. 如果 structured_metrics 为空 → 用 LLM 报告中的数据点 (data_points_by_section)
        3. 如果也没有 → AI 图片生成（ComfyUI）
        4. AI 失败 → 用 sample data 画 matplotlib 统计图
        5. matplotlib 失败 → 关键词卡片（无虚假数字）
        6. 关键词卡片失败 → 占位图

        Args:
            topic: 报告主题
            insights: 分析洞察列表
            dimensions: 分析维度列表
            data_points_by_section: LLM 在报告中显式给出的数据点
            structured_metrics: AnalyzerAgent 提取的结构化指标（优先级最高）

        Returns:
            配图数据列表
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

            # ─── 策略 0: 优先用 AnalyzerAgent 结构化指标（最高优先级）───
            chart_generated = False
            if structured_metrics:
                # 按维度匹配结构化指标
                dim_metrics = [
                    m for m in structured_metrics
                    if m.dimension and m.dimension.strip() == dim.strip()
                ]
                if not dim_metrics:
                    # 维度名不匹配时，尝试模糊匹配
                    dim_lower = dim.lower()
                    dim_metrics = [
                        m for m in structured_metrics
                        if m.dimension and (
                            m.dimension.lower() in dim_lower or dim_lower in m.dimension.lower()
                        )
                    ]

                for metric in dim_metrics[:2]:  # 每个维度最多 2 张图
                    if len(metric.data_points) < 2:
                        continue
                    try:
                        chart_type = metric.chart_type_hint
                        if chart_type not in ("bar", "line", "pie"):
                            chart_type = "bar"
                        chart_result = self.image_service.generate_matplotlib_chart(
                            section_title=metric.metric_name,
                            content="",
                            data_points=[
                                {"label": dp.label, "value": dp.value}
                                for dp in metric.data_points
                            ],
                            chart_type=chart_type,
                        )
                        if chart_result:
                            illustrations.append({
                                "section": dim,
                                "title": chart_result["title"],
                                "base64": chart_result["base64"],
                                "position": position_counter,
                                "source": "structured_metric",
                            })
                            position_counter += 1
                            successful_dimensions.add(dim)
                            chart_generated = True
                            logger.info(
                                f"[STRUCTURED-METRIC] Chart for '{dim}': "
                                f"'{metric.metric_name}' ({len(metric.data_points)} pts)"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Structured metric chart failed for '{dim}': "
                            f"{type(e).__name__}: {e}",
                        )

            # ─── 策略 1: 用真实数据点画统计图（来自 LLM 报告）───
            if not chart_generated and len(real_data_points) >= 3:
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

    def _build_chart_data_from_metrics(self, metric) -> Optional[Dict[str, Any]]:
        """Convert a StructuredMetric into Chart.js chart_data config."""
        if not metric.data_points or len(metric.data_points) < 2:
            return None
        labels = [dp.label for dp in metric.data_points]
        values = [dp.value for dp in metric.data_points]
        chart_type = metric.chart_type_hint if metric.chart_type_hint in ("bar", "line", "pie") else "bar"
        if chart_type == "pie":
            return {
                "labels": labels,
                "datasets": [{"label": metric.metric_name, "data": values}],
                "options": {
                    "plugins": {"legend": {"labels": {"color": "var(--text-2)"}}}
                },
            }
        return {
            "labels": labels,
            "datasets": [{"label": metric.metric_name, "data": values}],
            "options": {
                "plugins": {"legend": {"labels": {"color": "var(--text-2)"}}},
                "scales": {
                    "x": {"ticks": {"color": "var(--text-2)"}, "grid": {"color": "var(--border)"}},
                    "y": {"ticks": {"color": "var(--text-2)"}, "grid": {"color": "var(--border)"}},
                },
            },
        }

    def _metric_to_layout_type(self, metric) -> str:
        """Choose the best chart layout name for a StructuredMetric."""
        hint = (metric.chart_type_hint or "bar").lower()
        if hint == "line":
            return "chart_line"
        if hint == "pie":
            return "chart_pie"
        return "chart_bar"

    @staticmethod
    def _convert_llm_pages_to_html(
        llm_pages: List[Dict[str, Any]],
        LayoutType,
    ) -> List:
        """将 LLM JSON 结构化页面转换为 HTMLPageModel 列表
        
        LLM 输出的 JSON 格式与 HTMLPageModel 几乎 1:1 对应，
        直接转换即可保留 LLM 精心构建的 chart_data/kpi_metrics/notes 等内容。
        """
        from app.services.html_report_generator import HTMLPageModel, HTMLTextBlock, HTMLImageBlock

        pages = []
        layout_str_to_enum = {}
        for lt in LayoutType:
            layout_str_to_enum[lt.value] = lt

        for lp in llm_pages:
            if not isinstance(lp, dict):
                continue

            # 解析 layout
            layout_str = lp.get("layout", "content")
            layout = layout_str_to_enum.get(layout_str, LayoutType.CONTENT)

            # 转换 text_blocks
            text_blocks = []
            for tb in (lp.get("text_blocks") or []):
                if isinstance(tb, dict):
                    text_blocks.append(HTMLTextBlock(
                        text=tb.get("text", ""),
                        emphasis=tb.get("emphasis", []),
                        is_bullet=tb.get("is_bullet", False),
                        is_lead=tb.get("is_lead", False),
                    ))
                elif isinstance(tb, str):
                    text_blocks.append(HTMLTextBlock(text=tb))

            # 转换 image_blocks（LLM 输出的是 image_hints，不是实际 base64）
            image_blocks = []
            for ib in (lp.get("image_blocks") or []):
                if isinstance(ib, dict):
                    image_blocks.append(HTMLImageBlock(
                        url=ib.get("url", ib.get("base64", "")),
                        caption=ib.get("caption", ""),
                        source=ib.get("source", ""),
                    ))

            # chart_data（LLM 输出的格式与 Chart.js 兼容）
            chart_data = lp.get("chart_data")
            if chart_data and isinstance(chart_data, dict):
                # 确保 labels 和 datasets 字段存在
                if "labels" not in chart_data or "datasets" not in chart_data:
                    chart_data = None

            # table_data
            table_data = lp.get("table_data")

            # kpi_metrics
            kpi_metrics = lp.get("kpi_metrics") or []

            pages.append(HTMLPageModel(
                title=lp.get("title", f"Page {len(pages)+1}"),
                layout=layout,
                kicker=lp.get("kicker", ""),
                text_blocks=text_blocks,
                image_blocks=image_blocks,
                kpi_metrics=kpi_metrics,
                table_data=table_data if isinstance(table_data, dict) else None,
                chart_data=chart_data,
                notes=lp.get("notes", ""),
            ))

        return pages

    def _build_html_report(
        self,
        topic: str,
        summary: str,
        insights: List[Insight],
        dimensions: List[str],
        structured_metrics: Optional[List[Any]] = None,
        theme: Optional[str] = None,
        user_images: Optional[List[Dict[str, Any]]] = None,
        web_images: Optional[List[Dict[str, Any]]] = None,
        extracted_pages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build a complete HTML report using the html-ppt design system.

        Generates a full presentation with cover, TOC, executive summary,
        dimension analysis pages with charts, KPI grids, and thanks page.

        Args:
            user_images: List of dicts with 'base64' and optional 'caption' keys
            web_images: List of dicts with 'base64', 'source_url', and optional 'caption' keys
            extracted_pages: If provided, use LLM's structured JSON pages instead of
                             building pages from insights/dimensions programmatically.
                             Format: [{"title":..., "layout":"cover", "text_blocks":[...],
                                      "kpi_metrics":[...], "chart_data":{...}, "notes":...}, ...]
        """
        from app.services.html_report_generator import (
            HTMLReportGenerator,
            HTMLPageModel,
            HTMLTextBlock,
            HTMLImageBlock,
            LayoutType,
        )
        from app.services.theme_selector import theme_selector

        if not theme:
            theme = theme_selector.select_theme(topic, summary)

        generator = HTMLReportGenerator(theme=theme)
        
        # 优先使用 LLM 的结构化 JSON 页面（更强的内容质量 + chart_data/kpi_metrics）
        use_llm_pages = bool(extracted_pages and isinstance(extracted_pages, list) and len(extracted_pages) > 2)
        if use_llm_pages:
            pages = self._convert_llm_pages_to_html(extracted_pages, LayoutType)
            logger.info(
                "_build_html_report: using %d LLM-structured pages (preferring JSON over programmatic)",
                len(pages),
            )
            # 仍然对 LLM 页面做图片分配
            has_images = bool(user_images or web_images)
            if has_images:
                try:
                    from app.services.image_assigner import image_assigner
                    assignments = image_assigner.assign(pages, web_images, user_images)
                    overflow_images: List[HTMLImageBlock] = []
                    for page_idx, img_blocks in assignments.items():
                        if page_idx == -1:
                            overflow_images = img_blocks
                        elif 0 <= page_idx < len(pages):
                            pages[page_idx].image_blocks = list(pages[page_idx].image_blocks) + img_blocks
                    if overflow_images:
                        pages.append(HTMLPageModel(
                            title="参考图集", layout=LayoutType.IMAGE_GRID,
                            kicker="Gallery", image_blocks=overflow_images, notes="额外参考图片",
                        ))
                except Exception as e:
                    logger.warning(f"ImageAssigner failed for LLM pages: {e}")
            # Thanks page
            pages.append(HTMLPageModel(
                title="Thank You", layout=LayoutType.THANKS,
                text_blocks=[HTMLTextBlock(
                    text=f"Report generated by SCDC AI Agent System — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )],
            ))
            return generator.generate(pages)

        # ── 以下为程序化路径（extracted_pages 为空时）──
        pages: List[HTMLPageModel] = []

        # 1) Cover page
        pages.append(HTMLPageModel(
            title=topic,
            layout=LayoutType.COVER,
            kicker="Market Insight Report",
            text_blocks=[
                HTMLTextBlock(text=summary[:200] if summary else ""),
                HTMLTextBlock(text="SCDC AI Agent System"),
                HTMLTextBlock(text=datetime.datetime.now().strftime("%Y-%m-%d")),
            ],
            notes=summary[:300] if summary else topic,
        ))

        # 2) TOC page
        toc_items = ["Executive Summary"] + list(dimensions) + ["Data Visualization", "Conclusion"]
        pages.append(HTMLPageModel(
            title="Contents",
            layout=LayoutType.TOC,
            text_blocks=[HTMLTextBlock(text=item) for item in toc_items],
        ))

        # 3) Executive Summary page
        if summary:
            paragraphs = [p.strip() for p in summary.split("\n") if p.strip()]
            text_blocks = [HTMLTextBlock(text=p, is_lead=(i == 0)) for i, p in enumerate(paragraphs[:4])]
            # Build a summary chart from dimension insight counts
            dim_counts = {}
            for ins in insights:
                dim = ins.dimension or "General"
                dim_counts[dim] = dim_counts.get(dim, 0) + 1
            summary_chart = None
            if dim_counts and len(dim_counts) >= 2:
                summary_chart = {
                    "labels": list(dim_counts.keys()),
                    "datasets": [{
                        "label": "Insights",
                        "data": list(dim_counts.values()),
                    }],
                }
            pages.append(HTMLPageModel(
                title="Executive Summary",
                layout=LayoutType.CONTENT,
                kicker="Summary",
                text_blocks=text_blocks,
                chart_data=summary_chart,
                notes=summary[:300],
            ))

        # 3.5) Global KPI overview from structured metrics (or insights fallback)
        if structured_metrics:
            all_kpi_items = []
            for m in structured_metrics[:6]:
                if m.data_points:
                    latest = m.data_points[-1]
                    change = ""
                    trend = "up"
                    if len(m.data_points) >= 2:
                        prev = m.data_points[-2].value
                        if prev != 0:
                            pct = ((latest.value - prev) / abs(prev)) * 100
                            change = f"{pct:+.1f}%"
                            trend = "up" if pct >= 0 else "down"
                    all_kpi_items.append({
                        "label": m.metric_name,
                        "value": f"{latest.value}{m.unit}",
                        "raw_value": latest.value,
                        "unit": m.unit,
                        "change": change,
                        "trend": trend,
                    })
        else:
            # Fallback: build KPI from insights (dimension stats + confidence)
            all_kpi_items = []
            for dim in dimensions[:4]:
                dim_ins = [i for i in insights if (i.dimension or "").strip() == dim.strip()]
                if dim_ins:
                    avg_conf = sum(i.confidence for i in dim_ins) / len(dim_ins)
                    all_kpi_items.append({
                        "label": dim[:10],
                        "value": f"{len(dim_ins)}条",
                        "raw_value": len(dim_ins),
                        "unit": "洞察",
                        "change": f"均置信度 {avg_conf:.0%}",
                        "trend": "up",
                    })
            logger.info(
                "KPI fallback: built %d items from insights (structured_metrics was empty)",
                len(all_kpi_items),
            )
        
        if all_kpi_items:
            pages.append(HTMLPageModel(
                title="Key Metrics Overview",
                layout=LayoutType.KPI_GRID,
                kicker="Overview",
                kpi_metrics=all_kpi_items[:4],
            ))

        # 4) Dimension analysis pages with charts and KPI
        dim_insights: Dict[str, List[Insight]] = {}
        for ins in insights:
            dim = ins.dimension or "General Analysis"
            dim_insights.setdefault(dim, []).append(ins)

        for dim in dimensions:
            dim_list = dim_insights.get(dim, [])
            # Section divider page
            pages.append(HTMLPageModel(
                title=dim,
                layout=LayoutType.SECTION,
                kicker=f"Section · {dimensions.index(dim) + 1:02d}",
            ))

            if dim_list:
                # Bullets page with key insights (more visual than plain content)
                bullet_blocks = []
                for ins in dim_list[:5]:
                    bullet_blocks.append(HTMLTextBlock(
                        text=ins.conclusion,
                        emphasis=[ins.conclusion[:25]],
                        is_bullet=True,
                    ))
                pages.append(HTMLPageModel(
                    title=f"{dim} — Key Findings",
                    layout=LayoutType.BULLETS,
                    kicker="Key Points",
                    text_blocks=bullet_blocks,
                ))

                # Content page with detailed analysis + chart
                text_blocks = []
                for ins in dim_list[:3]:
                    if ins.analysis:
                        text_blocks.append(HTMLTextBlock(text=ins.analysis[:300]))
                if text_blocks:
                    # Build a chart from insight confidence scores
                    insight_chart = None
                    if len(dim_list) >= 2:
                        insight_chart = {
                            "labels": [ins.conclusion[:15] for ins in dim_list[:6]],
                            "datasets": [{
                                "label": "Confidence",
                                "data": [round(ins.confidence, 2) for ins in dim_list[:6]],
                            }],
                        }
                    pages.append(HTMLPageModel(
                        title=f"{dim} — Detailed Analysis",
                        layout=LayoutType.CONTENT,
                        kicker="Analysis",
                        text_blocks=text_blocks,
                        chart_data=insight_chart,
                    ))

                # Chart pages from structured metrics (or insights fallback)
                if structured_metrics:
                    dim_metrics = [
                        m for m in structured_metrics
                        if m.dimension and m.dimension.strip() == dim.strip()
                    ]

                    # KPI grid page
                    kpi_items = []
                    for m in dim_metrics[:4]:
                        if m.data_points:
                            latest = m.data_points[-1]
                            change = ""
                            trend = "up"
                            if len(m.data_points) >= 2:
                                prev = m.data_points[-2].value
                                if prev != 0:
                                    pct = ((latest.value - prev) / abs(prev)) * 100
                                    change = f"{pct:+.1f}%"
                                    trend = "up" if pct >= 0 else "down"
                            kpi_items.append({
                                "label": m.metric_name,
                                "value": f"{latest.value}{m.unit}",
                                "raw_value": latest.value,
                                "unit": m.unit,
                                "change": change,
                                "trend": trend,
                            })
                    if kpi_items:
                        pages.append(HTMLPageModel(
                            title=f"{dim} — Key Metrics",
                            layout=LayoutType.KPI_GRID,
                            kicker="Metrics",
                            kpi_metrics=kpi_items,
                        ))

                    # Chart visualization pages (one per metric with chart data)
                    for metric in dim_metrics[:2]:
                        chart_data = self._build_chart_data_from_metrics(metric)
                        if chart_data:
                            layout_name = self._metric_to_layout_type(metric)
                            chart_layout = getattr(LayoutType, layout_name.upper(), LayoutType.CHART_BAR)
                            source_text = f"Source: {metric.source}" if metric.source else ""
                            pages.append(HTMLPageModel(
                                title=metric.metric_name,
                                layout=chart_layout,
                                kicker=f"{dim} · {metric.metric_type}",
                                chart_data=chart_data,
                                text_blocks=[HTMLTextBlock(text=source_text)] if source_text else [],
                            ))

                    # Table page for metrics summary
                    if len(dim_metrics) >= 2:
                        headers = ["Metric", "Latest Value", "Unit", "Type"]
                        rows = []
                        for m in dim_metrics[:6]:
                            latest_val = str(m.data_points[-1].value) if m.data_points else "N/A"
                            rows.append([m.metric_name, latest_val, m.unit, m.metric_type])
                        pages.append(HTMLPageModel(
                            title=f"{dim} — Data Summary",
                            layout=LayoutType.TABLE,
                            kicker="Data",
                            table_data={"headers": headers, "rows": rows},
                        ))
                else:
                    # Fallback: no structured_metrics → create stat/chart page from insights
                    if dim_list:
                        avg_conf = sum(i.confidence for i in dim_list) / len(dim_list)
                        pages.append(HTMLPageModel(
                            title=f"{dim} — Key Findings",
                            layout=LayoutType.STAT_HIGHLIGHT,
                            kicker="Key Stat",
                            kpi_metrics=[{
                                "label": f"Insight Count",
                                "value": f"{len(dim_list):.0f}",
                                "raw_value": len(dim_list),
                            }],
                            text_blocks=[HTMLTextBlock(
                                text=f"{len(dim_list)} insights found for this dimension (avg confidence: {avg_conf:.1%})"
                            )],
                        ))
            else:
                pages.append(HTMLPageModel(
                    title=dim,
                    layout=LayoutType.CONTENT,
                    kicker="Pending Analysis",
                    text_blocks=[HTMLTextBlock(text="Insufficient data for this dimension.")],
                ))

        # 5) Global metrics overview (if we have structured_metrics across dimensions)
        if structured_metrics:
            # Stat highlight page for the most important metric
            all_metrics_with_data = [m for m in structured_metrics if m.data_points]
            if all_metrics_with_data:
                # Pick the metric with the most data points as the headline stat
                headline = max(all_metrics_with_data, key=lambda m: len(m.data_points))
                if headline.data_points:
                    latest = headline.data_points[-1]
                    pages.append(HTMLPageModel(
                        title=headline.metric_name,
                        layout=LayoutType.STAT_HIGHLIGHT,
                        kicker="Headline Metric",
                        kpi_metrics=[{
                            "label": headline.metric_name,
                            "value": f"{latest.value}",
                            "raw_value": latest.value,
                            "unit": headline.unit,
                        }],
                        text_blocks=[HTMLTextBlock(text=f"Latest data: {latest.label}")],
                    ))

        # 6) 智能图片分配：按内容相关性将图片分散到各页面（图文结合）
        #    对标豆                    ))

        # 6) 智能图片分配：LLM 路径和程序化路径都执行
        #    对标豆包/千问的思路：不在末尾堆图集，而是每页配相关图片
        has_images = bool(user_images or web_images)
        if has_images:
            try:
                from app.services.image_assigner import image_assigner
                assignments = image_assigner.assign(pages, web_images, user_images)
                # 注入分配的图片到对应页面
                overflow_images: List[HTMLImageBlock] = []
                for page_idx, img_blocks in assignments.items():
                    if page_idx == -1:
                        overflow_images = img_blocks
                    elif 0 <= page_idx < len(pages):
                        pages[page_idx].image_blocks = list(pages[page_idx].image_blocks) + img_blocks
                # 剩余的溢出图片放入独立图集页（如果有的话）
                if overflow_images:
                    pages.append(HTMLPageModel(
                        title="参考图集",
                        layout=LayoutType.IMAGE_GRID,
                        kicker="Gallery",
                        image_blocks=overflow_images,
                        notes="额外参考图片",
                    ))
                logger.info(
                    f"ImageAssigner distributed {sum(len(v) for v in assignments.values())} images "
                    f"across {sum(1 for k, v in assignments.items() if k >= 0 and v)} pages"
                )
            except Exception as e:
                logger.warning(f"ImageAssigner failed (fallback to gallery): {e}")
                # fallback: 全部放图集页（旧行为）
                all_images: List[HTMLImageBlock] = []
                for img in (user_images or []):
                    b64 = img.get("base64", "")
                    if b64:
                        all_images.append(HTMLImageBlock(
                            url=f"data:image/png;base64,{b64}",
                            caption=img.get("caption", ""),
                            source="user_upload",
                        ))
                for img in (web_images or []):
                    b64 = img.get("base64", "")
                    if b64:
                        all_images.append(HTMLImageBlock(
                            url=f"data:image/png;base64,{b64}",
                            caption=img.get("caption", "") or img.get("title", ""),
                            source=img.get("source_url", ""),
                        ))
                if all_images:
                    pages.append(HTMLPageModel(
                        title="参考图片",
                        layout=LayoutType.IMAGE_GRID,
                        kicker="Gallery",
                        image_blocks=all_images,
                        notes="用户上传及网页提取的参考图片",
                    ))

        # 7) Thanks page
        pages.append(HTMLPageModel(
            title="Thank You",
            layout=LayoutType.THANKS,
            text_blocks=[HTMLTextBlock(text=f"Report generated by SCDC AI Agent System — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")],
        ))

        return generator.generate(pages)

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
                    # 尝试从 LLM 输出末尾的 json 代码块提取结构化 PageModel
                    extracted_pages, extracted_theme, extracted_notes = (
                        self._extract_pages_from_llm_response(llm_report)
                    )
                    if extracted_pages is not None:
                        logger.info(
                            "ReporterAgent: LLM structured JSON extracted successfully: "
                            "%d pages, theme=%s, notes_summary=%d chars (task=%s)",
                            len(extracted_pages), extracted_theme or "(default)",
                            len(extracted_notes or ""), input_data.task_id,
                        )
                    else:
                        logger.info(
                            "LLM did not return structured PageModel JSON for task '%s', "
                            "falling back to MarkdownPageParser pipeline.",
                            input_data.task_id,
                        )

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
                            structured_metrics=input_data.analyzer_output.structured_metrics,
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
                        f"({len(full_markdown)} chars, pages={len(extracted_pages) if extracted_pages else 0})"
                    )

                    # Build HTML report
                    dims_for_html = dimensions if dimensions else DEFAULT_DIMENSIONS
                    html_content = ""
                    try:
                        html_content = self._build_html_report(
                            topic=input_data.topic,
                            summary=summary,
                            insights=insights,
                            dimensions=dims_for_html,
                            structured_metrics=input_data.analyzer_output.structured_metrics,
                            theme=extracted_theme,
                            user_images=input_data.user_images,
                            web_images=input_data.web_images,
                            extracted_pages=extracted_pages,
                        )
                        logger.info(f"HTML report generated ({len(html_content)} chars)")
                    except Exception as e:
                        logger.warning(f"HTML report generation failed: {e}")

                    return ReporterOutput(
                        task_id=input_data.task_id,
                        success=True,
                        markdown_report=full_markdown,
                        sections=sections,
                        chart_configs=chart_configs,
                        chart_images=chart_images,
                        dimension_illustrations=dimension_illustrations,
                        pages=extracted_pages or [],
                        theme=extracted_theme or "minimal-white",
                        notes_summary=extracted_notes or "",
                        html_content=html_content,
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
                structured_metrics=input_data.analyzer_output.structured_metrics,
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

        # Build HTML report for template path
        dims_for_html = dimensions if dimensions else DEFAULT_DIMENSIONS
        html_content = ""
        try:
            html_content = self._build_html_report(
                topic=input_data.topic,
                summary=summary,
                insights=insights,
                dimensions=dims_for_html,
                structured_metrics=input_data.analyzer_output.structured_metrics,
                user_images=input_data.user_images,
                web_images=input_data.web_images,
                extracted_pages=None,  # template路径无LLM页面
            )
            logger.info(f"HTML report generated for template path ({len(html_content)} chars)")
        except Exception as e:
            logger.warning(f"HTML report generation failed for template path: {e}")

        return ReporterOutput(
            task_id=input_data.task_id,
            success=True,
            markdown_report=full_markdown,
            sections=sections,
            chart_configs=chart_configs,
            chart_images=chart_images,
            dimension_illustrations=dimension_illustrations,
            pages=[],
            theme="minimal-white",
            notes_summary="",
            html_content=html_content,
            degraded=True,
        )

    async def execute_with_html_pipeline(
        self,
        input_data: ReporterInput,
        template_id: Optional[str] = None,
    ) -> Tuple[ReporterOutput, Optional[ReportPageModel], Optional[ValidationResult]]:
        """执行报告生成 + HTML 生成流程
        
        新流程：
        1. 执行现有报告生成逻辑（生成 Markdown）
        2. 将 Markdown 转换为带有布局信息的 PageModel
        3. 返回 PageModel 供 HTML 生成使用
        
        Returns:
            (ReporterOutput, ReportPageModel | None, ValidationResult | None)
        """
        # 1. 执行现有报告生成逻辑
        output = await self.execute(input_data)
        if not output.success or not output.markdown_report:
            return output, None, None
        
        try:
            # 2. Markdown → ReportPageModel（带布局信息）
            from app.services.html_report_generator import HTMLPageModel, HTMLTextBlock, HTMLImageBlock, LayoutType
            
            parser = MarkdownPageParser()
            chart_images = output.chart_images or []
            if output.dimension_illustrations:
                chart_images = list(chart_images) + list(output.dimension_illustrations)
            
            # 先用现有方法生成基础模型
            model = parser.parse(
                markdown=output.markdown_report,
                title=input_data.topic,
                chart_images=chart_images,
                metadata={
                    "task_id": input_data.task_id,
                    "dimensions": input_data.dimensions or list(DEFAULT_DIMENSIONS),
                    "degraded": output.degraded,
                },
            )
            
            # 3. 布局决策已下沉到 ReportService._choose_layout,
            #    不再在 ReporterAgent 中预设置 layout_hint.
            logger.info(
                "ReportPageModel built for task '%s': %d pages (layout decided later in _choose_layout)",
                input_data.task_id, model.page_count,
            )
            
            # 4. 质量校验 + 自动修复
            validator = QualityValidator()
            validation = validator.validate(model)
            
            if validation.fixes_applied:
                logger.info(
                    "QualityValidator applied %d fixes for task '%s': %s",
                    len(validation.fixes_applied), input_data.task_id,
                    validation.fixes_applied,
                )
            
            # 5. 将校验结果信息附加到输出
            final_model = validation.fixed_model or model
            output.metadata = output.metadata or {}
            output.metadata["quality_validation"] = {
                "passed": validation.passed,
                "errors": len(validation.errors),
                "warnings": len(validation.warnings),
                "fixes": len(validation.fixes_applied),
                "fixes_detail": validation.fixes_applied,
                "page_count": final_model.page_count,
            }
            
            return output, final_model, validation
            
        except Exception as e:
            logger.error(
                "HTML pipeline failed for task '%s': %s. "
                "Falling back to original output.",
                input_data.task_id, e, exc_info=True,
            )
            return output, None, None
    
    def _enhance_layout_info(
        self,
        pages: List[PageModel],
        chart_images: List[Dict[str, Any]],
    ) -> List[PageModel]:
        """DEPRECATED: 布局决策已统一移至 ReportService._choose_layout

        历史：此方法曾把 layout_hint 字符串写入 PageModel,
        然后由 ReportService._convert_pages_to_html 二次映射到 LayoutType.
        两层映射容易失同步, 维护成本高. 现已合并到 _choose_layout.

        保留为 no-op 桩以保持向后兼容 (外部脚本/测试可能直接调用).
        建议调用方: 直接传 ReportPageModel 给 ReportService.export_report_with_html_pipeline().
        """
        logger.debug(
            "ReporterAgent._enhance_layout_info is deprecated and a no-op; "
            "layout decision now happens in ReportService._choose_layout."
        )
        return pages