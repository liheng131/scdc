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
    r"C:\Windows\Fonts\simkai.ttf",
    r"C:\Windows\Fonts\STKAITI.TTF",
    r"C:\Windows\Fonts\STSONG.TTF",
    r"C:\Windows\Fonts\STXIHEI.TTF",
    r"C:\Windows\Fonts\STXINGKA.TTF",
    r"C:\Windows\Fonts\FZShuSong-Z01S.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Models/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Songti.ttc",
    # Linux (Debian/Ubuntu)
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
    # Linux (Noto CJK - common in Docker)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    # Linux (Source Han Sans / Adobe)
    "/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf",
    "/usr/share/fonts/source-han-sans/SourceHanSansSC-Regular.otf",
    "/usr/share/fonts/truetype/source-han-sans/SourceHanSansSC-Regular.ttf",
    # Linux (User-installed)
    "/root/.fonts/NotoSansCJK-Regular.ttc",
    "/root/.fonts/msyh.ttc",
    "/root/.fonts/wqy-microhei.ttc",
    "/root/.fonts/wqy-zenhei.ttc",
    # Linux (Local)
    "/usr/local/share/fonts/NotoSansCJK-Regular.ttc",
    "/usr/local/share/fonts/msyh.ttc",
    "/usr/local/share/fonts/wqy-microhei.ttc",
    "/usr/local/share/fonts/wqy-zenhei.ttc",
]
_sans_candidates = [
    "Microsoft YaHei", "SimHei", "SimSun", "DengXian", "STKaiti", "STSong",
    "PingFang SC", "STHeiti", "Songti SC", "Hiragino Sans GB",
    "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
    "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans CJK",
    "Source Han Sans SC", "Source Han Sans CN",
    "AR PL UMing CN", "AR PL UKai CN",
    "DejaVu Sans",
]
_font_loaded = False
_loaded_font_name = None
# 容错:即使所有字体都加载失败,也要让 _font_loaded 至少有默认值
for _fp in _font_paths:
    try:
        if os.path.exists(_fp):
            fm.fontManager.addfont(_fp)
            logger.info("ReportImageService: registered Chinese font: %s", _fp)
            _font_loaded = True
            # 记录实际加载的字体名
            try:
                _font_name = fm.FontProperties(fname=_fp).get_name()
                _loaded_font_name = _font_name
                logger.debug("ReportImageService: font name resolved to: %s", _font_name)
            except Exception as _ne:
                logger.debug("ReportImageService: failed to resolve font name for %s: %s", _fp, _ne)
            # 不 break,继续尝试加载其他字体(让 matplotlib 内部字体池更丰富)
    except Exception as _e:
        logger.warning("ReportImageService: failed to register font %s: %s", _fp, _e)
        continue

# 确保 _font_loaded 变量始终有定义(默认值 False)
if not isinstance(_font_loaded, bool):
    _font_loaded = False

# 配置 matplotlib 使用合适的字体
try:
    # 优先使用实际加载的字体名,否则使用候选列表
    if _loaded_font_name:
        _font_list = [_loaded_font_name] + _sans_candidates
    else:
        _font_list = _sans_candidates
    matplotlib.rcParams['font.sans-serif'] = _font_list
    matplotlib.rcParams['font.family'] = 'sans-serif'
    matplotlib.rcParams['axes.unicode_minus'] = False
    logger.debug(
        "ReportImageService: matplotlib font config done, _font_loaded=%s, font_list head=%s",
        _font_loaded, _font_list[:3] if _font_list else []
    )
except Exception as _rc_e:
    # 即使 rcParams 设置失败,也不能让模块导入失败
    logger.warning("ReportImageService: failed to set matplotlib rcParams: %s", _rc_e)
    try:
        matplotlib.rcParams['axes.unicode_minus'] = False
    except Exception:
        pass

logger.info(
    "ReportImageService font init: _font_loaded=%s, loaded_name=%s, paths_tried=%d",
    _font_loaded, _loaded_font_name, len(_font_paths)
)
del _font_paths, _fp, _sans_candidates, _font_list
# 保留 _loaded_font_name 和 _font_loaded 作为模块级状态,供其他方法查询


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
        timeout: int = 30,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        调用 ImageGenerationService 生成单张图片

        Args:
            prompt: 图像描述提示词
            timeout: 超时时间（秒），默认 30 秒
            **kwargs: 传递给 ImageGenerationService 的额外参数

        Returns:
            生成结果字典，包含 image_url 或 base64 等信息
        """
        try:
            # 使用较短的超时时间（30s）避免长时间等待
            result = await self.image_service.generate_image(
                prompt=prompt,
                timeout=timeout,
                **kwargs
            )
            
            # SubTask 3.1: 空值检测 - 检查 AI 返回是否为空
            if result is None:
                logger.warning("AI returned None for image generation")
                return None
            
            # 检查 image_url 和 base64 是否都为空
            image_url = result.get("image_url")
            base64_data = result.get("base64")
            
            if not image_url and not base64_data:
                logger.warning(
                    "AI returned empty image data (no image_url and no base64), "
                    f"prompt: {prompt[:100]}..."
                )
                # 仍然返回 result，让上层判断如何处理
            elif not image_url:
                logger.info("AI returned base64 image only (no image_url)")
            elif not base64_data:
                logger.info("AI returned image_url only (no base64)")
            else:
                logger.info("AI returned both image_url and base64")
            
            return result
            
        except TimeoutError as e:
            # SubTask 3.2: 区分超时异常
            logger.error(
                f"Timeout ({timeout}s) generating section image: {e}\n"
                f"Prompt: {prompt[:100]}...",
                exc_info=True
            )
            return None
        except ConnectionError as e:
            # 区分连接错误
            logger.error(
                f"Connection error generating section image: {e}\n"
                f"Prompt: {prompt[:100]}...",
                exc_info=True
            )
            return None
        except Exception as e:
            # 其他异常
            logger.error(
                f"Failed to generate section image: {type(e).__name__}: {e}\n"
                f"Prompt: {prompt[:100]}...",
                exc_info=True
            )
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
        generation_stats = {"ai": 0, "matplotlib": 0, "placeholder": 0, "failed": 0}
        
        for section_info in sections:
            section_name = section_info["section"]
            section_position = section_info["position"]
            
            # SubTask 3.3: 尝试 AI 生成图片
            gen_result = None
            ai_error = None
            try:
                gen_result = await self.generate_section_image(
                    prompt=section_info["prompt"]
                )
            except Exception as e:
                ai_error = e
                logger.error(
                    f"Error calling AI generation for section '{section_name}': "
                    f"{type(e).__name__}: {e}",
                    exc_info=True
                )
            
            # SubTask 3.3: 检查 AI 生成是否成功（同时检查 image_url 和 base64）
            if gen_result and (gen_result.get("image_url") or gen_result.get("base64")):
                # AI 生成成功
                image_results.append({
                    "section": section_name,
                    "title": f"{section_name} - AI生成配图",
                    "base64": gen_result.get("base64", ""),
                    "image_url": gen_result.get("image_url", ""),
                    "position": section_position,
                    "source": "ai"  # SubTask 3.4: 添加 source 字段
                })
                generation_stats["ai"] += 1
                logger.info(
                    f"[AI] Generated AI image for section '{section_name}' "
                    f"at position {section_position} "
                    f"(url={'yes' if gen_result.get('image_url') else 'no'}, "
                    f"base64={'yes' if gen_result.get('base64') else 'no'})"
                )
            else:
                # AI 生成失败，使用 matplotlib 降级方案
                if ai_error:
                    logger.warning(
                        f"[AI-FAIL] AI generation raised exception for '{section_name}': "
                        f"{ai_error}, falling back to matplotlib"
                    )
                elif gen_result is None:
                    logger.warning(
                        f"[AI-FAIL] AI generation returned None for '{section_name}', "
                        f"falling back to matplotlib"
                    )
                else:
                    logger.warning(
                        f"[AI-FAIL] AI generation returned empty data for '{section_name}' "
                        f"(image_url={gen_result.get('image_url')!r}, "
                        f"base64={'<empty>' if not gen_result.get('base64') else '<present>'}), "
                        f"falling back to matplotlib"
                    )
                
                # SubTask 3.3: 确保 chart_type 是有效的
                try:
                    chart_type = self._determine_chart_type(section_name)
                    valid_chart_types = {"bar", "pie", "line", "radar"}
                    if chart_type not in valid_chart_types:
                        logger.warning(
                            f"Invalid chart_type '{chart_type}' for '{section_name}', "
                            f"defaulting to 'bar'"
                        )
                        chart_type = "bar"
                    
                    chart_result = self.generate_matplotlib_chart(
                        section_title=section_name,
                        content=section_info["content"],
                        chart_type=chart_type
                    )
                    
                    if chart_result and chart_result.get("base64"):
                        # Matplotlib 成功
                        image_results.append({
                            "section": section_name,
                            "title": chart_result["title"],
                            "base64": chart_result["base64"],
                            "position": section_position,
                            "source": "matplotlib"  # SubTask 3.4: 添加 source 字段
                        })
                        generation_stats["matplotlib"] += 1
                        logger.info(
                            f"[MATPLOTLIB] Generated matplotlib chart for section "
                            f"'{section_name}' (chart_type={chart_type})"
                        )
                    else:
                        # Matplotlib 也失败，使用占位图
                        logger.warning(
                            f"[MATPLOTLIB-FAIL] Matplotlib generation failed for "
                            f"'{section_name}', using placeholder"
                        )
                        placeholder = self._generate_placeholder_image(section_name)
                        if placeholder:
                            image_results.append({
                                "section": section_name,
                                "title": placeholder["title"],
                                "base64": placeholder["base64"],
                                "position": section_position,
                                "source": "placeholder"  # SubTask 3.4: 添加 source 字段
                            })
                            generation_stats["placeholder"] += 1
                        else:
                            generation_stats["failed"] += 1
                            logger.error(
                                f"[FAILED] All image generation methods failed for "
                                f"'{section_name}', skipping"
                            )
                except Exception as fallback_error:
                    logger.error(
                        f"[MATPLOTLIB-ERROR] Matplotlib fallback exception for "
                        f"'{section_name}': {type(fallback_error).__name__}: "
                        f"{fallback_error}",
                        exc_info=True
                    )
                    # 尝试占位图
                    try:
                        placeholder = self._generate_placeholder_image(section_name)
                        if placeholder:
                            image_results.append({
                                "section": section_name,
                                "title": placeholder["title"],
                                "base64": placeholder["base64"],
                                "position": section_position,
                                "source": "placeholder"
                            })
                            generation_stats["placeholder"] += 1
                        else:
                            generation_stats["failed"] += 1
                    except Exception as placeholder_error:
                        logger.error(
                            f"[PLACEHOLDER-ERROR] Placeholder generation also failed "
                            f"for '{section_name}': {placeholder_error}",
                            exc_info=True
                        )
                        generation_stats["failed"] += 1

        # SubTask 3.4: 输出详细的生成统计日志
        logger.info(
            f"Report {report_id} image generation complete: "
            f"{len(image_results)}/{len(sections)} images generated | "
            f"AI: {generation_stats['ai']}, "
            f"Matplotlib: {generation_stats['matplotlib']}, "
            f"Placeholder: {generation_stats['placeholder']}, "
            f"Failed: {generation_stats['failed']}"
        )
        # 输出每个章节使用的生成方式
        for img in image_results:
            logger.debug(
                f"Report {report_id} section '{img['section']}': source={img.get('source', 'unknown')}"
            )

        return image_results

    def _generate_placeholder_image(self, section_title: str) -> Optional[Dict[str, str]]:
        """
        生成占位图（最终降级方案）

        Args:
            section_title: 章节标题

        Returns:
            包含 base64 编码图片的字典，失败返回 None
        """
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(
                0.5, 0.5,
                f"{section_title}\n\n(Image generation unavailable)",
                ha='center', va='center',
                fontsize=18, fontweight='bold',
                color='gray'
            )
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')

            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=80, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()

            return {
                "title": f"{section_title} - 占位图",
                "base64": b64
            }
        except Exception as e:
            logger.error(f"Failed to generate placeholder for '{section_title}': {e}")
            return None
    
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
        fig = None
        try:
            logger.debug(
                f"[MATPLOTLIB] generate_matplotlib_chart start: "
                f"section='{section_title}', chart_type='{chart_type}', "
                f"font_loaded={_font_loaded}, content_len={len(content or '')}"
            )

            # 步骤 1: 从内容中提取数据点(容错:任何异常都返回空列表)
            data_points: List[Dict[str, Any]] = []
            try:
                data_points = self._extract_data_from_content(content or "")
            except Exception as _ex_e:
                logger.warning(
                    f"[MATPLOTLIB] _extract_data_from_content raised exception: "
                    f"{type(_ex_e).__name__}: {_ex_e}"
                )
                data_points = []

            # 步骤 2: 数据不足(<2)或提取失败,使用示例数据
            if not data_points or len(data_points) < 2:
                logger.info(
                    f"[MATPLOTLIB] Insufficient data extracted from '{section_title}' "
                    f"(got {len(data_points)} points), falling back to sample data"
                )
                try:
                    data_points = self._generate_sample_data(section_title)
                except Exception as _sd_e:
                    logger.error(
                        f"[MATPLOTLIB] _generate_sample_data failed: "
                        f"{type(_sd_e).__name__}: {_sd_e}"
                    )
                    data_points = []

            # 步骤 3: 极端情况下 sample_data 也失败,使用硬编码占位数据
            if not data_points:
                logger.warning(
                    f"[MATPLOTLIB] All data sources failed for '{section_title}', "
                    f"using hardcoded placeholder data"
                )
                data_points = [
                    {"label": "Item 1", "value": 30.0},
                    {"label": "Item 2", "value": 45.0},
                    {"label": "Item 3", "value": 25.0},
                ]

            try:
                labels = [str(dp.get("label", "")) for dp in data_points]
                values = [float(dp.get("value", 0) or 0) for dp in data_points]
            except Exception as _lv_e:
                logger.error(
                    f"[MATPLOTLIB] Failed to build labels/values: "
                    f"{type(_lv_e).__name__}: {_lv_e}"
                )
                labels = ["A", "B", "C"]
                values = [30.0, 45.0, 25.0]

            # 如果中文字体未加载,将中文标签转为英文以避免渲染失败
            if not _font_loaded:
                logger.warning(
                    f"[MATPLOTLIB] Chinese font not loaded, "
                    f"replacing Chinese labels with English for '{section_title}'"
                )
                try:
                    labels = [f"Item {i+1}" for i in range(len(labels))]
                except Exception:
                    labels = [f"Item {i+1}" for i in range(len(values))]
                section_title = f"Chart for {section_title}"

            # 创建图表 - 即使字体渲染失败也要生成图(中文可能显示为方块)
            try:
                fig, ax = plt.subplots(figsize=(10, 6))
            except Exception as _fig_e:
                logger.error(
                    f"[MATPLOTLIB] plt.subplots failed for '{section_title}': "
                    f"{type(_fig_e).__name__}: {_fig_e}"
                )
                return None

            # 根据图表类型生成不同的图表 - 每个分支独立 try/except
            chart_rendered = False
            try:
                if chart_type == "pie" and 2 <= len(values) <= 8:
                    self._create_pie_chart(ax, labels, values, section_title)
                    chart_rendered = True
                elif chart_type == "line":
                    self._create_line_chart(ax, labels, values, section_title)
                    chart_rendered = True
                elif chart_type == "radar" and len(values) >= 3:
                    self._create_radar_chart(fig, labels, values, section_title)
                    chart_rendered = True
                else:
                    self._create_bar_chart(ax, labels, values, section_title)
                    chart_rendered = True
            except Exception as _render_e:
                logger.error(
                    f"[MATPLOTLIB] chart rendering failed for '{section_title}' "
                    f"(chart_type={chart_type}): {type(_render_e).__name__}: {_render_e}",
                    exc_info=True
                )
                # 渲染失败:尝试降级到最简化的柱状图
                try:
                    ax.clear()
                    self._create_bar_chart(ax, labels, values, section_title)
                    chart_rendered = True
                except Exception as _fallback_e:
                    logger.error(
                        f"[MATPLOTLIB] fallback bar chart also failed: "
                        f"{type(_fallback_e).__name__}: {_fallback_e}"
                    )
                    chart_rendered = False

            if not chart_rendered:
                if fig is not None:
                    try:
                        plt.close(fig)
                    except Exception:
                        pass
                return None

            # tight_layout 也可能因字体问题失败
            try:
                plt.tight_layout()
            except Exception as _tl_e:
                logger.debug(
                    f"[MATPLOTLIB] plt.tight_layout failed (non-fatal): {_tl_e}"
                )

            # 转换为 base64
            try:
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
                plt.close(fig)
                fig = None
                buf.seek(0)
                b64 = base64.b64encode(buf.read()).decode()
            except Exception as _save_e:
                logger.error(
                    f"[MATPLOTLIB] savefig/base64 failed for '{section_title}': "
                    f"{type(_save_e).__name__}: {_save_e}",
                    exc_info=True
                )
                if fig is not None:
                    try:
                        plt.close(fig)
                    except Exception:
                        pass
                return None

            if not b64:
                logger.error(
                    f"[MATPLOTLIB] Generated empty base64 for '{section_title}'"
                )
                return None

            logger.info(
                f"[MATPLOTLIB] Successfully generated chart for '{section_title}': "
                f"chart_type={chart_type}, points={len(values)}, "
                f"b64_len={len(b64)}"
            )

            return {
                "title": f"{section_title} - 统计图表",
                "base64": b64
            }

        except Exception as e:
            logger.error(
                f"[MATPLOTLIB] Unexpected error generating chart for "
                f"'{section_title}': {type(e).__name__}: {e}",
                exc_info=True
            )
            if fig is not None:
                try:
                    plt.close(fig)
                except Exception:
                    pass
            return None
    
    def _extract_data_from_content(self, content: str) -> List[Dict[str, Any]]:
        """
        从内容中提取关键数据点用于图表生成

        健壮性保证:任何异常(正则编译失败、空内容、超长文本)都返回空列表,
        让调用方降级到 _generate_sample_data。

        Args:
            content: 章节内容

        Returns:
            数据点列表，每个包含 label 和 value
        """
        # 防御性:空内容/非字符串直接返回空
        if not content or not isinstance(content, str):
            logger.debug("[EXTRACT] empty or invalid content, returning []")
            return []

        # 截断超长内容,避免正则灾难性回溯
        max_content_len = 50000
        if len(content) > max_content_len:
            logger.debug(
                f"[EXTRACT] content too long ({len(content)} > {max_content_len}), "
                f"truncating"
            )
            content = content[:max_content_len]

        data_points: List[Dict[str, Any]] = []

        # 尝试提取百分比数据 (如 "30%", "45.5%")
        try:
            percentage_pattern = r'([\u4e00-\u9fa5\w\s]+?)[：:为占达]*\s*(\d+(?:\.\d+)?)\s*%'
            percentage_matches = re.findall(percentage_pattern, content)
            if percentage_matches:
                for label, value in percentage_matches[:8]:
                    try:
                        label = (label or "").strip()
                        if label and len(label) < 20:
                            data_points.append({
                                "label": label,
                                "value": float(value)
                            })
                    except Exception:
                        continue
                if data_points:
                    logger.debug(
                        f"[EXTRACT] extracted {len(data_points)} percentage data points"
                    )
                    return data_points
        except Exception as _pe:
            logger.debug(f"[EXTRACT] percentage pattern failed: {_pe}")

        # 尝试提取数值数据 (如 "100万", "5000元", "200人")
        try:
            number_pattern = r'([\u4e00-\u9fa5\w\s]+?)[：:为达]*\s*(\d+(?:\.\d+)?)\s*(?:万|亿|元|人|家|个|台|套)'
            number_matches = re.findall(number_pattern, content)
            if number_matches:
                for label, value in number_matches[:8]:
                    try:
                        label = (label or "").strip()
                        if label and len(label) < 20:
                            data_points.append({
                                "label": label,
                                "value": float(value)
                            })
                    except Exception:
                        continue
                if data_points:
                    logger.debug(
                        f"[EXTRACT] extracted {len(data_points)} number data points"
                    )
                    return data_points
        except Exception as _ne:
            logger.debug(f"[EXTRACT] number pattern failed: {_ne}")

        # 尝试提取简单的数字列表
        try:
            simple_pattern = r'(?:^|\n)\s*[-•·]\s*([\u4e00-\u9fa5\w\s]+?)[：:为]*\s*(\d+(?:\.\d+)?)'
            simple_matches = re.findall(simple_pattern, content)
            if simple_matches:
                for label, value in simple_matches[:8]:
                    try:
                        label = (label or "").strip()
                        if label and len(label) < 20:
                            data_points.append({
                                "label": label,
                                "value": float(value)
                            })
                    except Exception:
                        continue
                if data_points:
                    logger.debug(
                        f"[EXTRACT] extracted {len(data_points)} simple list data points"
                    )
                    return data_points
        except Exception as _se:
            logger.debug(f"[EXTRACT] simple list pattern failed: {_se}")

        if not data_points:
            logger.debug(
                f"[EXTRACT] no data points extracted from content "
                f"(content_len={len(content)})"
            )
        return data_points
    
    def _generate_sample_data(self, section_title: str) -> List[Dict[str, Any]]:
        """
        根据维度类型生成示例数据

        始终返回非空数据点列表(至少 3 个)。如果章节标题不匹配任何已知维度,
        基于文本长度生成合理的随机分布数据。

        Args:
            section_title: 章节标题

        Returns:
            示例数据点列表(永不为空)
        """
        # 防御性:处理 None 或非字符串
        if not section_title or not isinstance(section_title, str):
            section_title = "default"

        title_lower = section_title.lower()

        try:
            # ── 维度匹配 - 优先匹配最具体的关键词 ──

            # 市场规模、市场细分、市场概况、市场概述 -> 增长型数据
            if any(kw in title_lower for kw in [
                "市场", "规模", "细分", "板块", "概况", "概述"
            ]):
                return [
                    {"label": "2020年", "value": 100},
                    {"label": "2021年", "value": 125},
                    {"label": "2022年", "value": 156},
                    {"label": "2023年", "value": 195},
                    {"label": "2024年", "value": 244},
                ]

            # 竞争分析、竞品分析 -> 市场份额
            elif any(kw in title_lower for kw in ["竞争", "竞品"]):
                return [
                    {"label": "公司A", "value": 35},
                    {"label": "公司B", "value": 28},
                    {"label": "公司C", "value": 20},
                    {"label": "其他", "value": 17},
                ]

            # 用户分析、用户画像 -> 年龄段分布
            elif "用户" in title_lower:
                return [
                    {"label": "18-24岁", "value": 25},
                    {"label": "25-34岁", "value": 38},
                    {"label": "35-44岁", "value": 22},
                    {"label": "45岁以上", "value": 15},
                ]

            # 趋势预测 -> 季度时间序列
            elif any(kw in title_lower for kw in ["趋势", "预测", "展望"]):
                return [
                    {"label": "Q1", "value": 85},
                    {"label": "Q2", "value": 92},
                    {"label": "Q3", "value": 105},
                    {"label": "Q4", "value": 118},
                    {"label": "下一年Q1", "value": 132},
                ]

            # 财务分析 -> 利润构成
            elif "财务" in title_lower:
                return [
                    {"label": "收入", "value": 580},
                    {"label": "成本", "value": 320},
                    {"label": "利润", "value": 260},
                    {"label": "税收", "value": 78},
                ]

            # 风险评估 -> 风险类型
            elif "风险" in title_lower:
                return [
                    {"label": "技术风险", "value": 30},
                    {"label": "市场风险", "value": 45},
                    {"label": "政策风险", "value": 25},
                    {"label": "运营风险", "value": 35},
                ]

            # 战略建议 -> 时间线
            elif any(kw in title_lower for kw in ["战略", "建议", "机会"]):
                return [
                    {"label": "短期策略", "value": 40},
                    {"label": "中期策略", "value": 35},
                    {"label": "长期策略", "value": 25},
                ]

            # 现状、总结、洞察 -> 关键指标
            elif any(kw in title_lower for kw in ["现状", "总结", "洞察"]):
                return [
                    {"label": "关键指标A", "value": 78},
                    {"label": "关键指标B", "value": 65},
                    {"label": "关键指标C", "value": 52},
                    {"label": "关键指标D", "value": 40},
                ]

            # 兜底:基于文本长度的智能默认数据
            else:
                return self._generate_intelligent_default(section_title)

        except Exception as _e:
            logger.error(
                f"[SAMPLE] _generate_sample_data failed for '{section_title}': "
                f"{type(_e).__name__}: {_e}"
            )
            # 最坏情况也要返回非空数据
            return [
                {"label": "Item 1", "value": 30.0},
                {"label": "Item 2", "value": 45.0},
                {"label": "Item 3", "value": 25.0},
            ]

    def _generate_intelligent_default(self, section_title: str) -> List[Dict[str, Any]]:
        """
        基于文本特征生成智能默认数据(兜底方案)

        Args:
            section_title: 章节标题

        Returns:
            数据点列表
        """
        try:
            # 基于文本长度生成基础值
            text_len = len(section_title or "")
            base = 30 + (text_len % 30)  # 30-60
            # 简单分布:递减或递增
            values = [
                float(base),
                float(base + 10 + (text_len % 5)),
                float(base + 5 + (text_len % 8)),
                float(max(5, base - 10)),
            ]
            # 取标题前 8 个字符作为系列名
            series_name = (section_title or "数据")[:8]
            return [
                {"label": f"{series_name}-A", "value": values[0]},
                {"label": f"{series_name}-B", "value": values[1]},
                {"label": f"{series_name}-C", "value": values[2]},
                {"label": f"{series_name}-D", "value": values[3]},
            ]
        except Exception as _e:
            logger.debug(f"[SAMPLE] intelligent default failed: {_e}")
            return [
                {"label": "类别A", "value": 45},
                {"label": "类别B", "value": 32},
                {"label": "类别C", "value": 28},
                {"label": "类别D", "value": 20},
            ]
    
    def _create_bar_chart(self, ax, labels: List[str], values: List[float], title: str):
        """创建柱状图 - 全部操作 try/except 包装,确保字体渲染失败也能输出图"""
        try:
            colors = plt.cm.Blues([(i + 2) / (len(values) + 2) for i in range(len(values))])
            bars = ax.bar(labels, values, color=colors, edgecolor='white', linewidth=1.5)

            # 添加数值标签
            try:
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.1f}',
                           ha='center', va='bottom', fontsize=10)
            except Exception as _te:
                logger.debug(f"[_BAR] text labels failed (non-fatal): {_te}")

            try:
                ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
            except Exception as _te:
                logger.debug(f"[_BAR] set_title failed (non-fatal): {_te}")
            try:
                ax.set_ylabel("数值", fontsize=12)
            except Exception:
                pass
            try:
                ax.grid(True, alpha=0.3, axis='y', linestyle='--')
            except Exception:
                pass
            try:
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
            except Exception:
                pass
        except Exception as _e:
            logger.error(
                f"[_BAR] bar chart creation failed: {type(_e).__name__}: {_e}"
            )
            raise

    def _create_pie_chart(self, ax, labels: List[str], values: List[float], title: str):
        """创建饼图 - 全部操作 try/except 包装"""
        try:
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
            try:
                for autotext in autotexts:
                    autotext.set_color('white')
                    autotext.set_fontweight('bold')
                    autotext.set_fontsize(10)
            except Exception as _te:
                logger.debug(f"[_PIE] text styling failed (non-fatal): {_te}")

            try:
                ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
            except Exception as _te:
                logger.debug(f"[_PIE] set_title failed (non-fatal): {_te}")
        except Exception as _e:
            logger.error(
                f"[_PIE] pie chart creation failed: {type(_e).__name__}: {_e}"
            )
            raise

    def _create_line_chart(self, ax, labels: List[str], values: List[float], title: str):
        """创建折线图 - 全部操作 try/except 包装"""
        try:
            ax.plot(labels, values, marker='o', linewidth=2.5, markersize=8,
                    color='#2E86AB', markerfacecolor='#A23B72', markeredgecolor='white', markeredgewidth=2)

            # 填充区域
            try:
                ax.fill_between(labels, values, alpha=0.2, color='#2E86AB')
            except Exception as _fe:
                logger.debug(f"[_LINE] fill_between failed (non-fatal): {_fe}")

            # 添加数值标签
            try:
                for i, (label, value) in enumerate(zip(labels, values)):
                    ax.text(i, value, f'{value:.1f}',
                           ha='center', va='bottom', fontsize=10, fontweight='bold')
            except Exception as _te:
                logger.debug(f"[_LINE] text labels failed (non-fatal): {_te}")

            try:
                ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
            except Exception as _te:
                logger.debug(f"[_LINE] set_title failed (non-fatal): {_te}")
            try:
                ax.set_ylabel("数值", fontsize=12)
            except Exception:
                pass
            try:
                ax.grid(True, alpha=0.3, linestyle='--')
            except Exception:
                pass
            try:
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
            except Exception:
                pass
        except Exception as _e:
            logger.error(
                f"[_LINE] line chart creation failed: {type(_e).__name__}: {_e}"
            )
            raise

    def _create_radar_chart(self, fig, labels: List[str], values: List[float], title: str):
        """创建雷达图 - 全部操作 try/except 包装"""
        try:
            # 计算角度
            angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()

            # 闭合数据
            values_closed = values + [values[0]]
            angles_closed = angles + [angles[0]]

            # 添加极坐标子图
            try:
                ax = fig.add_subplot(111, polar=True)
            except Exception as _ae:
                logger.error(f"[_RADAR] add_subplot failed: {_ae}")
                raise

            # 绘制雷达图
            try:
                ax.plot(angles_closed, values_closed, 'o-', linewidth=2, color='#2E86AB')
                ax.fill(angles_closed, values_closed, alpha=0.25, color='#2E86AB')
            except Exception as _pe:
                logger.debug(f"[_RADAR] plot/fill failed (non-fatal): {_pe}")

            # 设置标签
            try:
                ax.set_xticks(angles)
                ax.set_xticklabels(labels, fontsize=11)
            except Exception as _te:
                logger.debug(f"[_RADAR] xticks/labels failed (non-fatal): {_te}")
            try:
                ax.set_ylim(0, max(values) * 1.2)
            except Exception:
                pass

            # 添加标题
            try:
                ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
            except Exception as _te:
                logger.debug(f"[_RADAR] set_title failed (non-fatal): {_te}")

            # 设置网格样式
            try:
                ax.grid(True, alpha=0.3, linestyle='--')
            except Exception:
                pass
        except Exception as _e:
            logger.error(
                f"[_RADAR] radar chart creation failed: {type(_e).__name__}: {_e}"
            )
            raise
