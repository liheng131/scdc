"""
报告配图生成服务

为报告的关键章节自动生成商业/数据可视化风格的配图。

核心功能：
- analyze_sections(): 分析报告 Markdown 内容，提取关键章节
- generate_section_image(): 调用 ImageGenerationService 生成单张图片
- generate_report_images(): 为报告生成配图的主方法
- generate_matplotlib_chart(): 降级方案，使用 matplotlib 生成统计图表

配图风格：
- 商业信息图、数据可视化、专业商务风格
- 使用英文 prompt（ComfyUI 对英文理解更好）
- 每个 prompt 控制在 50-80 词
"""

import base64
import io
import logging
import os
import re
from typing import List, Dict, Any, Optional, Tuple

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

from app.services.image_generation import ImageGenerationService

logger = logging.getLogger(__name__)

# ── Chinese font configuration for matplotlib ──────────────────────────
_font_paths = [
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Songti.ttc",
    # Linux (Docker)
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
]
_sans_candidates = [
    "Microsoft YaHei", "SimHei", "SimSun", "DengXian",
    "PingFang SC", "STHeiti", "Songti SC",
    "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
    "Noto Sans CJK SC", "Noto Sans CJK",
    "DejaVu Sans",
]
_font_loaded = False
for _fp in _font_paths:
    if os.path.exists(_fp):
        try:
            fm.fontManager.addfont(_fp)
            logger.info("ReportImageService: registered Chinese font: %s", _fp)
            _font_loaded = True
        except Exception as _e:
            logger.warning("ReportImageService: failed to register font %s: %s", _fp, _e)
        break
matplotlib.rcParams['font.sans-serif'] = _sans_candidates
matplotlib.rcParams['axes.unicode_minus'] = False
del _font_paths, _fp, _sans_candidates


# 常见报告章节类型到配图风格的映射模板
SECTION_STYLE_TEMPLATES = {
    "市场概况": {
        "base_prompt": "A professional business infographic showing market size and growth trends, clean modern style, blue and green color scheme",
        "keywords": ["market", "size", "growth", "trends", "data visualization", "business chart"]
    },
    "市场规模": {
        "base_prompt": "A sleek business dashboard displaying market size metrics with bar charts and pie charts, modern flat design, professional blue and teal palette",
        "keywords": ["market size", "metrics", "dashboard", "charts", "analytics"]
    },
    "竞争分析": {
        "base_prompt": "A competitive landscape analysis diagram showing company positioning matrix, clean corporate style, gradient blue tones with white background",
        "keywords": ["competitive", "landscape", "matrix", "positioning", "comparison"]
    },
    "竞品分析": {
        "base_prompt": "A product comparison visualization with feature matrices and radar charts, modern infographics style, blue and orange accent colors",
        "keywords": ["product comparison", "features", "radar chart", "competitive analysis"]
    },
    "用户分析": {
        "base_prompt": "User demographic data visualization with persona illustrations and statistical charts, modern UX design style, purple and blue gradients",
        "keywords": ["user demographics", "personas", "statistics", "audience", "analytics"]
    },
    "趋势预测": {
        "base_prompt": "Future trend forecast visualization with line graphs and growth curves, futuristic business style, dark blue background with neon accents",
        "keywords": ["forecast", "trends", "growth", "projections", "future"]
    },
    "财务分析": {
        "base_prompt": "Financial performance dashboard with revenue charts, profit margins, and key metrics, professional accounting style, green and gold color scheme",
        "keywords": ["financial", "revenue", "profit", "metrics", "accounting"]
    },
    "风险评估": {
        "base_prompt": "Risk assessment matrix visualization with heat map and probability charts, corporate risk management style, red and grey tones",
        "keywords": ["risk", "assessment", "matrix", "heatmap", "probability"]
    },
    "战略建议": {
        "base_prompt": "Strategic planning roadmap illustration with milestones and timeline, executive presentation style, navy blue and white with accent colors",
        "keywords": ["strategy", "roadmap", "planning", "milestones", "timeline"]
    },
    "执行摘要": {
        "base_prompt": "Executive summary overview infographic with key highlights and summary metrics, boardroom presentation style, elegant dark theme with gold accents",
        "keywords": ["executive", "summary", "highlights", "overview", "key points"]
    },
    "行业分析": {
        "base_prompt": "Industry analysis infographic showing ecosystem map and value chain, professional consulting style, blue and grey corporate palette",
        "keywords": ["industry", "ecosystem", "value chain", "analysis", "consulting"]
    },
    "技术发展": {
        "base_prompt": "Technology evolution timeline with innovation milestones and tech stack diagrams, modern tech presentation style, cyan and dark blue gradient",
        "keywords": ["technology", "evolution", "innovation", "timeline", "tech stack"]
    },
    "政策法规": {
        "base_prompt": "Regulatory compliance framework visualization with policy hierarchy chart, formal government style, navy blue and white with official seal elements",
        "keywords": ["regulation", "compliance", "policy", "framework", "government"]
    },
    "供应链": {
        "base_prompt": "Supply chain network diagram with flow visualization and logistics map, modern operations style, green and blue tones",
        "keywords": ["supply chain", "logistics", "network", "flow", "operations"]
    },
    "营销策略": {
        "base_prompt": "Marketing strategy funnel visualization with conversion metrics and channel breakdown, digital marketing style, vibrant multi-color palette",
        "keywords": ["marketing", "funnel", "conversion", "channels", "campaign"]
    },
    "运营分析": {
        "base_prompt": "Operations analytics dashboard with KPI gauges and performance metrics, business intelligence style, blue and grey modern design",
        "keywords": ["operations", "KPI", "performance", "analytics", "dashboard"]
    },
    "产品介绍": {
        "base_prompt": "Product showcase presentation with feature highlights and value proposition, modern product marketing style, clean white with brand colors",
        "keywords": ["product", "showcase", "features", "value proposition", "marketing"]
    },
    "团队介绍": {
        "base_prompt": "Team organization chart with role descriptions and skill matrix, professional HR style, warm blue and grey tones",
        "keywords": ["team", "organization", "roles", "skills", "structure"]
    },
    "总结": {
        "base_prompt": "Project summary infographic with key achievements and future outlook, executive presentation style, professional blue and white theme",
        "keywords": ["summary", "achievements", "outlook", "conclusion", "recap"]
    },
    "附录": {
        "base_prompt": "Reference data visualization with tables and supplementary charts, academic report style, clean black and white with subtle blue accents",
        "keywords": ["reference", "data", "tables", "supplementary", "appendix"]
    },
}

# 通用配图模板（用于无法匹配到具体章节类型时）
DEFAULT_PROMPT_TEMPLATES = [
    "A professional business data visualization with charts and graphs, modern corporate style, blue and white color scheme, clean minimalist design",
    "An infographic showing key business metrics and insights, contemporary flat design, teal and navy blue palette with white space",
    "A strategic analysis diagram with interconnected nodes and flow indicators, consulting presentation style, gradient blue tones",
    "A comprehensive report summary visual with highlighted key points and statistics, executive dashboard style, dark blue background",
    "A modern business concept illustration showing growth and success themes, professional corporate style, green and blue gradients",
]


class ReportImageService:
    """报告配图生成服务"""

    def __init__(self, image_service: Optional[ImageGenerationService] = None):
        self.image_service = image_service or ImageGenerationService()

    def analyze_sections(self, content_markdown: str) -> List[Dict[str, Any]]:
        """
        分析报告 Markdown 内容，提取关键章节并为每个章节生成配图 prompt

        Args:
            content_markdown: 报告的 Markdown 内容

        Returns:
            章节信息列表，每个包含：
            - section: 章节标题
            - content: 章节内容摘要
            - prompt: 为该章节生成的英文配图 prompt
            - position: 章节在报告中的位置索引
        """
        if not content_markdown:
            return []

        # 提取所有二级标题（##）作为关键章节
        sections = self._extract_sections(content_markdown)
        
        if not sections:
            # 如果没有找到标题，尝试使用一级标题
            sections = self._extract_sections(content_markdown, level=1)
        
        # 为每个章节生成配图 prompt
        section_info_list = []
        for idx, section in enumerate(sections):
            prompt = self._generate_section_prompt(section["title"], section["content"])
            section_info_list.append({
                "section": section["title"],
                "content": section["content"][:200],  # 内容摘要
                "prompt": prompt,
                "position": idx + 1
            })

        return section_info_list

    def _extract_sections(
        self, 
        content_markdown: str, 
        level: int = 2
    ) -> List[Dict[str, str]]:
        """
        从 Markdown 中提取章节

        Args:
            content_markdown: Markdown 内容
            level: 标题级别（2 表示 ##，1 表示 #）

        Returns:
            章节列表，每个包含 title 和 content
        """
        prefix = "#" * level + " "
        pattern = re.compile(rf'^{re.escape(prefix)}(.+)$', re.MULTILINE)
        
        matches = list(pattern.finditer(content_markdown))
        
        if not matches:
            return []

        sections = []
        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content_markdown)
            content = content_markdown[start:end].strip()
            
            sections.append({
                "title": title,
                "content": content
            })

        return sections

    def _generate_section_prompt(self, title: str, content: str) -> str:
        """
        为指定章节生成英文配图 prompt

        Args:
            title: 章节标题
            content: 章节内容

        Returns:
            50-80 词的英文 prompt
        """
        # 尝试匹配预定义的章节类型
        matched_template = self._match_section_type(title, content)
        
        if matched_template:
            prompt = self._enhance_prompt(matched_template, title, content)
        else:
            # 使用默认模板
            prompt = self._create_default_prompt(title, content)
        
        # 确保 prompt 长度在 50-80 词之间
        prompt = self._adjust_prompt_length(prompt)
        
        return prompt

    def _match_section_type(self, title: str, content: str) -> Optional[Dict]:
        """
        根据章节标题和内容匹配预定义的章节类型

        Args:
            title: 章节标题
            content: 章节内容

        Returns:
            匹配的模板字典，或 None
        """
        title_lower = title.lower()
        content_lower = content.lower()[:500]  # 仅使用前 500 字符
        combined = f"{title_lower} {content_lower}"
        
        # 直接匹配标题
        for section_type, template in SECTION_STYLE_TEMPLATES.items():
            if section_type.lower() in title_lower:
                return template
        
        # 基于关键词匹配
        for section_type, template in SECTION_STYLE_TEMPLATES.items():
            for keyword in template["keywords"]:
                if keyword.lower() in combined:
                    return template
        
        return None

    def _enhance_prompt(
        self, 
        template: Dict, 
        title: str, 
        content: str
    ) -> str:
        """
        根据章节内容增强基础 prompt

        Args:
            template: 预定义模板
            title: 章节标题
            content: 章节内容

        Returns:
            增强后的完整 prompt
        """
        base_prompt = template["base_prompt"]
        
        # 从内容中提取关键数据点
        key_elements = self._extract_key_elements(content)
        
        # 构建增强 prompt
        enhanced = f"{base_prompt}, featuring {key_elements}"
        enhanced += ", high quality, professional business presentation style, clean typography"
        enhanced += ", suitable for corporate report, white background with subtle shadows"
        
        return enhanced

    def _extract_key_elements(self, content: str) -> str:
        """
        从章节内容中提取关键元素用于 prompt 生成

        Args:
            content: 章节内容

        Returns:
            关键元素描述字符串
        """
        elements = []
        content_lower = content.lower()
        
        # 检查数据相关关键词
        data_indicators = {
            "百分比": "percentage data points",
            "增长率": "growth rate indicators",
            "趋势": "trend lines",
            "对比": "comparison charts",
            "排名": "ranking visualization",
            "占比": "proportion pie chart",
            "分布": "distribution diagram",
            "预测": "forecast projection",
            "目标": "target markers",
            "实际": "actual performance bars",
        }
        
        for keyword, element in data_indicators.items():
            if keyword in content_lower:
                elements.append(element)
        
        if not elements:
            elements = ["key metrics and insights"]
        
        # 最多取 3 个元素
        return ", ".join(elements[:3])

    def _create_default_prompt(self, title: str, content: str) -> str:
        """
        为无法匹配的章节创建默认 prompt

        Args:
            title: 章节标题
            content: 章节内容

        Returns:
            默认 prompt
        """
        # 使用标题生成个性化 prompt
        base = f"A professional business infographic related to {title}"
        base += ", modern corporate design style with data visualization elements"
        base += ", clean layout with charts and graphics, blue and grey color palette"
        base += ", high quality, suitable for business report, white background"
        base += ", professional typography and visual hierarchy"
        
        return base

    def _adjust_prompt_length(self, prompt: str, min_words: int = 50, max_words: int = 80) -> str:
        """
        调整 prompt 长度到指定词数范围

        Args:
            prompt: 原始 prompt
            min_words: 最小词数
            max_words: 最大词数

        Returns:
            调整后的 prompt
        """
        words = prompt.split()
        word_count = len(words)
        
        if word_count < min_words:
            # 补充描述性词汇
            additions = [
                "high resolution", "detailed", "polished", "refined",
                "award-winning design", "corporate standard", "publication quality",
                "modern aesthetics", "clean composition", "balanced layout"
            ]
            for addition in additions:
                if word_count >= min_words:
                    break
                words.extend(addition.split())
                word_count = len(words)
        
        elif word_count > max_words:
            # 截断到最大词数
            words = words[:max_words]
        
        return " ".join(words)

    async def generate_section_image(
        self,
        prompt: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        调用 ImageGenerationService 生成单张图片

        Args:
            prompt: 图像描述提示词
            **kwargs: 传递给 ImageGenerationService 的额外参数

        Returns:
            生成结果字典，包含 image_url 等信息
        """
        try:
            result = await self.image_service.generate_image(prompt=prompt, **kwargs)
            return result
        except Exception as e:
            logger.error(f"Failed to generate section image: {e}")
            return None

    async def generate_report_images(
        self,
        report_id: int,
        content_markdown: str,
        max_images: int = 3
    ) -> List[Dict[str, Any]]:
        """
        为报告生成配图的主方法

        流程：
        1. 分析内容提取关键章节
        2. 为每个关键章节生成 prompt
        3. 调用 ComfyUI 生成图片
        4. 如果 AI 生成失败，使用 matplotlib 生成统计图（降级方案）
        5. 返回配图列表

        Args:
            report_id: 报告 ID
            content_markdown: 报告 Markdown 内容
            max_images: 最大生成图片数量

        Returns:
            配图列表，每个包含：
            - section: 章节名称
            - title: 图表标题
            - base64: base64 编码的图片
            - position: 在报告中的位置
        """
        if not content_markdown:
            logger.warning(f"No content provided for report {report_id}")
            return []

        # 步骤 1: 分析内容提取关键章节
        sections = self.analyze_sections(content_markdown)
        
        if not sections:
            logger.info(f"No sections found in report {report_id}")
            return []

        # 限制最大图片数量
        sections = sections[:max_images]
        
        logger.info(
            f"Generating {len(sections)} images for report {report_id}: "
            f"{[s['section'] for s in sections]}"
        )

        # 步骤 2 & 3: 为每个章节生成图片
        image_results = []
        for section_info in sections:
            try:
                # 尝试 AI 生成图片
                gen_result = await self.generate_section_image(
                    prompt=section_info["prompt"]
                )
                
                if gen_result and gen_result.get("image_url"):
                    image_results.append({
                        "section": section_info["section"],
                        "title": f"{section_info['section']} - AI生成配图",
                        "base64": gen_result.get("base64", ""),
                        "position": section_info["position"]
                    })
                    logger.info(
                        f"Generated AI image for section '{section_info['section']}' "
                        f"at position {section_info['position']}"
                    )
                else:
                    # AI 生成失败，使用 matplotlib 降级方案
                    logger.warning(
                        f"AI generation failed for section '{section_info['section']}', "
                        f"falling back to matplotlib"
                    )
                    chart_type = self._determine_chart_type(section_info["section"])
                    chart_result = self.generate_matplotlib_chart(
                        section_title=section_info["section"],
                        content=section_info["content"],
                        chart_type=chart_type
                    )
                    
                    if chart_result:
                        image_results.append({
                            "section": section_info["section"],
                            "title": chart_result["title"],
                            "base64": chart_result["base64"],
                            "position": section_info["position"]
                        })
                        logger.info(
                            f"Generated matplotlib chart for section '{section_info['section']}'"
                        )
                    
            except Exception as e:
                logger.error(
                    f"Error generating image for section '{section_info['section']}': {e}"
                )
                # 异常情况下也尝试 matplotlib 降级
                try:
                    chart_type = self._determine_chart_type(section_info["section"])
                    chart_result = self.generate_matplotlib_chart(
                        section_title=section_info["section"],
                        content=section_info["content"],
                        chart_type=chart_type
                    )
                    if chart_result:
                        image_results.append({
                            "section": section_info["section"],
                            "title": chart_result["title"],
                            "base64": chart_result["base64"],
                            "position": section_info["position"]
                        })
                except Exception as fallback_error:
                    logger.error(
                        f"Matplotlib fallback also failed for '{section_info['section']}': {fallback_error}"
                    )
                continue

        logger.info(
            f"Successfully generated {len(image_results)}/{len(sections)} "
            f"images for report {report_id}"
        )

        return image_results
    
    def _determine_chart_type(self, section_title: str) -> str:
        """
        根据章节标题确定图表类型
        
        Args:
            section_title: 章节标题
            
        Returns:
            图表类型 ("bar", "pie", "line", "radar")
        """
        title_lower = section_title.lower()
        
        # 市场规模、财务分析、风险评估 -> 柱状图
        if any(keyword in title_lower for keyword in ["市场", "规模", "财务", "风险"]):
            return "bar"
        
        # 竞争分析、用户分析、战略建议 -> 饼图
        elif any(keyword in title_lower for keyword in ["竞争", "用户", "战略", "建议"]):
            return "pie"
        
        # 趋势预测 -> 折线图
        elif any(keyword in title_lower for keyword in ["趋势", "预测"]):
            return "line"
        
        # 竞品分析 -> 雷达图
        elif "竞品" in title_lower:
            return "radar"
        
        # 默认使用柱状图
        else:
            return "bar"

    def generate_matplotlib_chart(
        self,
        section_title: str,
        content: str,
        chart_type: str = "bar"
    ) -> Optional[Dict[str, str]]:
        """
        使用 matplotlib 生成统计图表（降级方案）

        Args:
            section_title: 章节标题
            content: 章节内容
            chart_type: 图表类型 ("bar", "pie", "line", "radar")

        Returns:
            包含 base64 编码图片的字典 {"title": str, "base64": str}，失败返回 None
        """
        try:
            # 从内容中提取数据点
            data_points = self._extract_data_from_content(content)
            
            if not data_points or len(data_points) < 2:
                # 如果没有足够数据，生成示例数据
                logger.info(f"Insufficient data in '{section_title}', using sample data")
                data_points = self._generate_sample_data(section_title)
            
            labels = [dp["label"] for dp in data_points]
            values = [dp["value"] for dp in data_points]
            
            # 如果中文字体未加载，将中文标签转为英文以避免渲染失败
            if not _font_loaded:
                logger.warning("Chinese font not loaded, using English labels as fallback")
                labels = [f"Item {i+1}" for i in range(len(labels))]
                section_title = f"Chart for {section_title}"
            
            # 创建图表
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # 根据图表类型生成不同的图表
            if chart_type == "pie" and 2 <= len(values) <= 8:
                self._create_pie_chart(ax, labels, values, section_title)
            elif chart_type == "line":
                self._create_line_chart(ax, labels, values, section_title)
            elif chart_type == "radar" and len(values) >= 3:
                self._create_radar_chart(fig, labels, values, section_title)
            else:  # default to bar
                self._create_bar_chart(ax, labels, values, section_title)
            
            plt.tight_layout()
            
            # 转换为 base64
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
            
            return {
                "title": f"{section_title} - 统计图表",
                "base64": b64
            }
            
        except Exception as e:
            logger.error(f"Failed to generate matplotlib chart for '{section_title}': {e}")
            return None
    
    def _extract_data_from_content(self, content: str) -> List[Dict[str, Any]]:
        """
        从内容中提取关键数据点用于图表生成
        
        Args:
            content: 章节内容
            
        Returns:
            数据点列表，每个包含 label 和 value
        """
        data_points = []
        
        # 尝试提取百分比数据 (如 "30%", "45.5%")
        percentage_pattern = r'([\u4e00-\u9fa5\w\s]+?)[：:为占达]*\s*(\d+(?:\.\d+)?)\s*%'
        percentage_matches = re.findall(percentage_pattern, content)
        if percentage_matches:
            for label, value in percentage_matches[:8]:
                label = label.strip()
                if label and len(label) < 20:
                    data_points.append({
                        "label": label,
                        "value": float(value)
                    })
            if data_points:
                return data_points
        
        # 尝试提取数值数据 (如 "100万", "5000元", "200人")
        number_pattern = r'([\u4e00-\u9fa5\w\s]+?)[：:为达]*\s*(\d+(?:\.\d+)?)\s*(?:万|亿|元|人|家|个|台|套)'
        number_matches = re.findall(number_pattern, content)
        if number_matches:
            for label, value in number_matches[:8]:
                label = label.strip()
                if label and len(label) < 20:
                    data_points.append({
                        "label": label,
                        "value": float(value)
                    })
            if data_points:
                return data_points
        
        # 尝试提取简单的数字列表
        simple_pattern = r'(?:^|\n)\s*[-•·]\s*([\u4e00-\u9fa5\w\s]+?)[：:为]*\s*(\d+(?:\.\d+)?)'
        simple_matches = re.findall(simple_pattern, content)
        if simple_matches:
            for label, value in simple_matches[:8]:
                label = label.strip()
                if label and len(label) < 20:
                    data_points.append({
                        "label": label,
                        "value": float(value)
                    })
            if data_points:
                return data_points
        
        return data_points
    
    def _generate_sample_data(self, section_title: str) -> List[Dict[str, Any]]:
        """
        根据维度类型生成示例数据
        
        Args:
            section_title: 章节标题
            
        Returns:
            示例数据点列表
        """
        title_lower = section_title.lower()
        
        # 根据维度类型生成合理的示例数据
        if "市场" in title_lower or "规模" in title_lower:
            return [
                {"label": "2020年", "value": 100},
                {"label": "2021年", "value": 125},
                {"label": "2022年", "value": 156},
                {"label": "2023年", "value": 195},
                {"label": "2024年", "value": 244},
            ]
        elif "竞争" in title_lower or "竞品" in title_lower:
            return [
                {"label": "公司A", "value": 35},
                {"label": "公司B", "value": 28},
                {"label": "公司C", "value": 20},
                {"label": "其他", "value": 17},
            ]
        elif "用户" in title_lower:
            return [
                {"label": "18-24岁", "value": 25},
                {"label": "25-34岁", "value": 38},
                {"label": "35-44岁", "value": 22},
                {"label": "45岁以上", "value": 15},
            ]
        elif "趋势" in title_lower or "预测" in title_lower:
            return [
                {"label": "Q1", "value": 85},
                {"label": "Q2", "value": 92},
                {"label": "Q3", "value": 105},
                {"label": "Q4", "value": 118},
                {"label": "下一年Q1", "value": 132},
            ]
        elif "财务" in title_lower:
            return [
                {"label": "收入", "value": 580},
                {"label": "成本", "value": 320},
                {"label": "利润", "value": 260},
                {"label": "税收", "value": 78},
            ]
        elif "风险" in title_lower:
            return [
                {"label": "技术风险", "value": 30},
                {"label": "市场风险", "value": 45},
                {"label": "政策风险", "value": 25},
                {"label": "运营风险", "value": 35},
            ]
        elif "战略" in title_lower or "建议" in title_lower:
            return [
                {"label": "短期策略", "value": 40},
                {"label": "中期策略", "value": 35},
                {"label": "长期策略", "value": 25},
            ]
        else:
            # 默认数据
            return [
                {"label": "类别A", "value": 45},
                {"label": "类别B", "value": 32},
                {"label": "类别C", "value": 28},
                {"label": "类别D", "value": 20},
            ]
    
    def _create_bar_chart(self, ax, labels: List[str], values: List[float], title: str):
        """创建柱状图"""
        colors = plt.cm.Blues([(i + 2) / (len(values) + 2) for i in range(len(values))])
        bars = ax.bar(labels, values, color=colors, edgecolor='white', linewidth=1.5)
        
        # 添加数值标签
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.1f}',
                   ha='center', va='bottom', fontsize=10)
        
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.set_ylabel("数值", fontsize=12)
        ax.grid(True, alpha=0.3, axis='y', linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
    
    def _create_pie_chart(self, ax, labels: List[str], values: List[float], title: str):
        """创建饼图"""
        colors = plt.cm.Set3([(i) / max(len(values) - 1, 1) for i in range(len(values))])
        wedges, texts, autotexts = ax.pie(
            values, 
            labels=labels, 
            autopct='%1.1f%%',
            colors=colors,
            startangle=90,
            wedgeprops=dict(width=0.7, edgecolor='white')
        )
        
        # 设置百分比文本样式
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(10)
        
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    
    def _create_line_chart(self, ax, labels: List[str], values: List[float], title: str):
        """创建折线图"""
        ax.plot(labels, values, marker='o', linewidth=2.5, markersize=8, 
                color='#2E86AB', markerfacecolor='#A23B72', markeredgecolor='white', markeredgewidth=2)
        
        # 填充区域
        ax.fill_between(labels, values, alpha=0.2, color='#2E86AB')
        
        # 添加数值标签
        for i, (label, value) in enumerate(zip(labels, values)):
            ax.text(i, value, f'{value:.1f}', 
                   ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.set_ylabel("数值", fontsize=12)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
    
    def _create_radar_chart(self, fig, labels: List[str], values: List[float], title: str):
        """创建雷达图"""
        # 计算角度
        angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        
        # 闭合数据
        values_closed = values + [values[0]]
        angles_closed = angles + [angles[0]]
        
        # 添加极坐标子图
        ax = fig.add_subplot(111, polar=True)
        
        # 绘制雷达图
        ax.plot(angles_closed, values_closed, 'o-', linewidth=2, color='#2E86AB')
        ax.fill(angles_closed, values_closed, alpha=0.25, color='#2E86AB')
        
        # 设置标签
        ax.set_xticks(angles)
        ax.set_xticklabels(labels, fontsize=11)
        ax.set_ylim(0, max(values) * 1.2)
        
        # 添加标题
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        
        # 设置网格样式
        ax.grid(True, alpha=0.3, linestyle='--')
