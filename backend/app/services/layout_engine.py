"""
LayoutEngine —— 智能布局引擎

对标 Beautiful.ai "Smart Slides" / 豆包模板匹配：
根据页面内容特征（文本长度、图片数量、KPI 数量等）自动选择最佳布局模板，
并处理溢出检测、字号调整和智能拆页。

每个 LayoutType 对应一组布局模板变体，引擎按条件评分匹配最优模板。

模板变体命名规则：{layout_type}-{variant_id}
- content-txt-img: 左文右图（文本 > 200 字 + 有图）
- content-img-txt: 上图下文（文本 100-300 字 + 有图）
- content-two-col: 双栏纯文本（文本 > 500 字 + 无图）
- content-single-col: 单栏纯文本（文本 < 500 字 + 无图）
- kpi-4col: 4 列 KPI（正好 4 个指标）
- kpi-3col: 3 列 KPI（3 个指标）
- kpi-2x2: 2x2 网格（2-4 个指标）
- bullets-card: 卡片式要点（每条要点带左侧色条）
- bullets-list: 列表式要点（简短列表）
- bullets-numbered: 编号式要点（有序列表）

溢出处理策略：
1. 文本 > 单页容量 → 根据标点符号智能拆分
2. 字号自适应：默认 18pt，溢出时降至 14pt（最少 12pt）
3. 图片 > 3 张 → 溢出到 IMAGE_GRID 页
"""

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.services.html_report_generator import (
    HTMLPageModel, HTMLTextBlock, HTMLImageBlock, LayoutType,
)

logger = logging.getLogger(__name__)

# 单页容量常数（与 report_page_model.py 的 MAX_CHARS_PER_PAGE 保持联动）
MAX_CHARS_PER_PAGE = 600  # 从 800 降低到 600，与商业平台一致（更多页、每页更清爽）
MAX_IMAGES_PER_PAGE = 3
MAX_BULLETS_PER_PAGE = 6
FONT_SIZE_DEFAULT = 18  # pt
FONT_SIZE_MIN = 12       # pt（低于此值说明内容太多，必须拆页）
FONT_SIZE_KPI_VALUE = 48  # pt（KPI 大数字）


class TemplateVariant(str, Enum):
    """布局模板变体"""
    # Content
    CONTENT_TXT_IMG = "content-txt-img"         # 左文 + 右图
    CONTENT_IMG_TXT = "content-img-txt"         # 上图 + 下文
    CONTENT_TWO_COL = "content-two-col"          # 双栏纯文本
    CONTENT_SINGLE_COL = "content-single-col"    # 单栏纯文本
    CONTENT_WIDE_IMG = "content-wide-img"        # 大图 + 底部文字
    # Bullets
    BULLETS_CARD = "bullets-card"                # 卡片式要点
    BULLETS_LIST = "bullets-list"                # 列表式要点
    BULLETS_NUMBERED = "bullets-numbered"        # 编号式要点
    # KPI Grid
    KPI_4COL = "kpi-4col"                        # 4 列
    KPI_3COL = "kpi-3col"                        # 3 列
    KPI_2X2 = "kpi-2x2"                          # 2x2 网格
    # Two Column
    TWO_COL_CARD = "two-col-card"                # 双栏卡片
    TWO_COL_COMPARE = "two-col-compare"          # 双栏对比
    # Three Column
    THREE_COL_CARD = "three-col-card"            # 三列卡片
    THREE_COL_ICON = "three-col-icon"            # 三列图标
    # Image
    IMAGE_HERO_FULL = "image-hero-full"          # 全屏大图
    IMAGE_GRID_3 = "image-grid-3"                # 3 列图集
    IMAGE_GRID_2 = "image-grid-2"                # 2 列图集
    # Table
    TABLE_WIDE = "table-wide"                    # 宽表格
    TABLE_CONDENSED = "table-condensed"          # 紧凑表格
    # Chart
    CHART_FULL = "chart-full"                    # 全页图表
    CHART_TXT = "chart-txt"                      # 文本 + 图表


# 每个模板变体的选择条件和规则
TEMPLATE_RULES: Dict[TemplateVariant, Dict[str, Any]] = {
    # ── Content 内容页 ──
    TemplateVariant.CONTENT_TXT_IMG: {
        "conditions": {
            "has_image": True,
            "total_chars": (200, 600),
        },
        "layout_params": {"text_ratio": 0.45, "image_ratio": 0.55, "image_placement": "right"},
    },
    TemplateVariant.CONTENT_IMG_TXT: {
        "conditions": {
            "has_image": True,
            "total_chars": (100, 300),
        },
        "layout_params": {"text_ratio": 0.4, "image_ratio": 0.6, "image_placement": "top"},
    },
    TemplateVariant.CONTENT_WIDE_IMG: {
        "conditions": {
            "has_image": True,
            "total_chars": (0, 150),
        },
        "layout_params": {"text_ratio": 0.3, "image_ratio": 0.7, "image_placement": "top"},
    },
    TemplateVariant.CONTENT_TWO_COL: {
        "conditions": {
            "has_image": False,
            "total_chars": (400, 9999),
        },
        "layout_params": {"columns": 2, "font_size": 16},
    },
    TemplateVariant.CONTENT_SINGLE_COL: {
        "conditions": {
            "has_image": False,
            "total_chars": (0, 400),
        },
        "layout_params": {"columns": 1, "font_size": 18},
        "default": True,  # fallback 兜底
    },
    # ── Bullets 要点页 ──
    TemplateVariant.BULLETS_CARD: {
        "conditions": {
            "bullet_count": (3, 6),
        },
        "layout_params": {"style": "card", "gap": "14px"},
        "default": True,
    },
    TemplateVariant.BULLETS_LIST: {
        "conditions": {
            "bullet_count": (1, 3),
        },
        "layout_params": {"style": "list", "gap": "10px"},
    },
    # ── KPI Grid ──
    TemplateVariant.KPI_4COL: {
        "conditions": {"kpi_count": 4},
        "layout_params": {"columns": 4, "value_font_size": 56},
    },
    TemplateVariant.KPI_3COL: {
        "conditions": {"kpi_count": 3},
        "layout_params": {"columns": 3, "value_font_size": 64},
    },
    TemplateVariant.KPI_2X2: {
        "conditions": {"kpi_count": (2, 4)},  # 2 或非精确 3/4 的都走 2x2
        "layout_params": {"columns": 2, "rows": 2, "value_font_size": 52},
        "default": True,
    },
    # ── Image ──
    TemplateVariant.IMAGE_HERO_FULL: {
        "conditions": {"image_count": 1},
        "layout_params": {"height": "480px", "object_fit": "contain"},
    },
    TemplateVariant.IMAGE_GRID_3: {
        "conditions": {"image_count": (3, 6)},
        "layout_params": {"columns": 3, "image_height": "240px"},
    },
    TemplateVariant.IMAGE_GRID_2: {
        "conditions": {"image_count": (1, 3)},
        "layout_params": {"columns": 2, "image_height": "320px"},
        "default": True,
    },
    # ── Table ──
    TemplateVariant.TABLE_WIDE: {
        "conditions": {"col_count": (4, 10)},
        "layout_params": {"font_size": 14, "compact": False},
        "default": True,
    },
    TemplateVariant.TABLE_CONDENSED: {
        "conditions": {"col_count": (1, 4)},
        "layout_params": {"font_size": 16, "compact": True},
    },
    # ── Chart ──
    TemplateVariant.CHART_FULL: {
        "conditions": {"total_chars": (0, 100)},
        "layout_params": {"chart_height": "520px"},
    },
    TemplateVariant.CHART_TXT: {
        "conditions": {"total_chars": (100, 9999)},
        "layout_params": {"chart_height": "320px"},
        "default": True,
    },
    # ── Other ──
    TemplateVariant.TWO_COL_CARD: {
        "default": True,
    },
    TemplateVariant.THREE_COL_CARD: {
        "default": True,
    },
}


@dataclass
class LayoutDecision:
    """布局决策结果"""
    variant: TemplateVariant
    layout_type: LayoutType
    params: Dict[str, Any] = field(default_factory=dict)
    overflow_pages: List["HTMLPageModel"] = field(default_factory=list)
    font_size: int = FONT_SIZE_DEFAULT
    warnings: List[str] = field(default_factory=list)

    @property
    def has_overflow(self) -> bool:
        return len(self.overflow_pages) > 0


class LayoutEngine:
    """智能布局引擎

    Usage:
        engine = LayoutEngine()
        decision = engine.decide(page_model)
        # decision.variant → 前端/渲染器根据 variant 选择对应 CSS/ppt layout
        # decision.overflow_pages → 需要拆分的额外页面
    """

    def __init__(self):
        pass

    def decide(self, page: HTMLPageModel) -> LayoutDecision:
        """为页面选择最佳布局模板

        Args:
            page: HTML 页面模型

        Returns:
            LayoutDecision: 包含模板变体、布局参数和溢出页
        """
        layout = page.layout

        # 分析页面内容特征
        features = self._analyze_features(page)
        logger.debug(f"LayoutEngine analyzing page '{page.title[:30]}': features={features}")

        # 检查溢出
        overflow_pages = []
        warnings = []
        font_size = FONT_SIZE_DEFAULT

        # 文本溢出检测
        if features["total_chars"] > MAX_CHARS_PER_PAGE:
            overflow_pages = self._split_overflow(page, features)
            warnings.append(
                f"Content exceeds {MAX_CHARS_PER_PAGE} chars "
                f"({features['total_chars']}), split into {len(overflow_pages)} extra pages"
            )

        # 字号自适应
        if features["total_chars"] > MAX_CHARS_PER_PAGE * 0.7:
            font_size = max(FONT_SIZE_MIN, int(18 - (features["total_chars"] - MAX_CHARS_PER_PAGE * 0.7) / 50))

        # 选择模板变体
        variant = self._match_template(layout, features)

        # 构建决策
        params = self._build_params(variant, features)
        if font_size != FONT_SIZE_DEFAULT:
            params["font_size"] = font_size

        return LayoutDecision(
            variant=variant,
            layout_type=layout,
            params=params,
            overflow_pages=overflow_pages,
            font_size=font_size,
            warnings=warnings,
        )

    def _analyze_features(self, page: HTMLPageModel) -> Dict[str, Any]:
        """提取页面内容特征"""
        total_chars = sum(len(tb.text) for tb in page.text_blocks)
        table_data = page.table_data
        col_count = len(table_data.get("headers", [])) if table_data else 0

        return {
            "total_chars": total_chars,
            "image_count": len(page.image_blocks),
            "has_image": len(page.image_blocks) > 0,
            "kpi_count": len(page.kpi_metrics),
            "bullet_count": sum(1 for tb in page.text_blocks if tb.is_bullet),
            "has_chart": page.chart_data is not None,
            "has_table": table_data is not None,
            "col_count": col_count,
            "layout_type": page.layout.value if page.layout else "content",
        }

    def _match_template(
        self, layout: LayoutType, features: Dict[str, Any]
    ) -> TemplateVariant:
        """根据布局类型和内容特征匹配最佳模板变体"""
        # 候选变体（当前布局类型对应的所有变体）
        candidates = [v for v in TemplateVariant if layout.value in v.value]

        best_variant = None
        best_score = -1

        for variant in candidates:
            rules = TEMPLATE_RULES.get(variant, {})
            if not rules:
                continue

            # 检查硬性条件
            conditions = rules.get("conditions", {})
            if not self._check_conditions(conditions, features):
                continue

            # 计算匹配得分
            score = self._score_match(conditions, features)
            if rules.get("default") and best_variant is None:
                # 兜底模板（条件不满足但无更好的选择）
                best_variant = variant
                best_score = 0

            if score > best_score:
                best_score = score
                best_variant = variant

        # 没找到匹配 → 选 default 变体
        if best_variant is None:
            for variant in candidates:
                if TEMPLATE_RULES.get(variant, {}).get("default"):
                    best_variant = variant
                    break
            if best_variant is None:
                # 最后的 fallback
                fallback_map = {
                    LayoutType.CONTENT: TemplateVariant.CONTENT_SINGLE_COL,
                    LayoutType.BULLETS: TemplateVariant.BULLETS_CARD,
                    LayoutType.KPI_GRID: TemplateVariant.KPI_2X2,
                    LayoutType.IMAGE_GRID: TemplateVariant.IMAGE_GRID_2,
                    LayoutType.IMAGE_HERO: TemplateVariant.IMAGE_HERO_FULL,
                    LayoutType.TABLE: TemplateVariant.TABLE_WIDE,
                }
                best_variant = fallback_map.get(layout, TemplateVariant.CONTENT_SINGLE_COL)

        logger.debug(f"LayoutEngine: layout={layout.value} → variant={best_variant.value}, score={best_score:.2f}")
        return best_variant

    def _check_conditions(self, conditions: Dict[str, Any], features: Dict[str, Any]) -> bool:
        """检查特征是否满足模板条件"""
        for key, expected in conditions.items():
            actual = features.get(key)
            if actual is None:
                return False
            if isinstance(expected, tuple):
                lo, hi = expected
                if not (lo <= actual <= hi):
                    return False
            elif isinstance(expected, (int, float, bool)):
                if actual != expected:
                    return False
            elif isinstance(expected, list):
                if actual not in expected:
                    return False
        return True

    def _score_match(self, conditions: Dict[str, Any], features: Dict[str, Any]) -> float:
        """计算特征匹配得分（0.0 - 1.0）"""
        if not conditions:
            return 0.5
        score = 0.0
        n = len(conditions)
        for key, expected in conditions.items():
            actual = features.get(key, 0)
            if isinstance(expected, tuple):
                lo, hi = expected
                mid = (lo + hi) / 2
                # 越接近区间中点得分越高
                if lo <= actual <= hi:
                    dist = abs(actual - mid)
                    half_range = (hi - lo) / 2
                    if half_range > 0:
                        score += 1.0 - (dist / half_range) * 0.5
                    else:
                        score += 1.0
            elif isinstance(expected, (int, float, bool)):
                score += 1.0 if actual == expected else 0.0
        return score / n if n > 0 else 0.5

    def _split_overflow(
        self, page: HTMLPageModel, features: Dict[str, Any]
    ) -> List[HTMLPageModel]:
        """文本溢出时智能拆分页面
        
        拆分策略：按标点符号寻找自然断点，每页不超过 MAX_CHARS_PER_PAGE
        """
        overflow_pages = []
        all_text = "\n\n".join(tb.text for tb in page.text_blocks)
        if len(all_text) <= MAX_CHARS_PER_PAGE:
            return overflow_pages

        # 按自然段分割
        paragraphs = [p.strip() for p in all_text.split("\n") if p.strip()]
        current_chars = 0
        current_paras = []

        for para in paragraphs:
            if current_chars + len(para) > MAX_CHARS_PER_PAGE and current_paras:
                # 当前段组已满，创建溢出页
                overflow_pages.append(HTMLPageModel(
                    title=f"{page.title} (续)",
                    layout=page.layout,
                    kicker=page.kicker,
                    text_blocks=[HTMLTextBlock(text="\n".join(current_paras))],
                ))
                current_paras = []
                current_chars = 0

            # 处理超长段落（单个段落超出容量）
            if len(para) > MAX_CHARS_PER_PAGE:
                # 按句子拆分
                sentences = self._split_by_sentence(para)
                for sent in sentences:
                    if current_chars + len(sent) > MAX_CHARS_PER_PAGE and current_paras:
                        overflow_pages.append(HTMLPageModel(
                            title=f"{page.title} (续)",
                            layout=page.layout,
                            kicker=page.kicker,
                            text_blocks=[HTMLTextBlock(text="\n".join(current_paras))],
                        ))
                        current_paras = []
                        current_chars = 0
                    current_paras.append(sent)
                    current_chars += len(sent)
            else:
                current_paras.append(para)
                current_chars += len(para)

        # 最后一段（修改原页面的 text_blocks）
        if current_paras:
            page.text_blocks = [HTMLTextBlock(
                text="\n".join(current_paras),
                is_lead=page.text_blocks[0].is_lead if page.text_blocks else False,
            )]

        return overflow_pages

    @staticmethod
    def _split_by_sentence(text: str, max_chars: int = MAX_CHARS_PER_PAGE) -> List[str]:
        """按句号/分号/换行拆分超长段落"""
        import re
        # 在标点后切分（保留标点）
        parts = re.split(r'(?<=[。；！？.!?;；\n])', text)
        groups = []
        current = ""
        for part in parts:
            if len(current) + len(part) > max_chars and current:
                groups.append(current)
                current = part
            else:
                current += part
        if current:
            groups.append(current)
        return groups if groups else [text]

    def _build_params(
        self, variant: TemplateVariant, features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """根据模板变体和内容特征构建布局参数"""
        rules = TEMPLATE_RULES.get(variant, {})
        params = dict(rules.get("layout_params", {}))

        # 动态调整：图片多 → 降低文字比例
        if features["has_image"] and features["image_count"] >= 2:
            params["text_ratio"] = params.get("text_ratio", 0.45) * 0.8
            params["image_ratio"] = 1.0 - params.get("text_ratio", 0.45)

        # 文字多 → 缩小字号
        if features["total_chars"] > MAX_CHARS_PER_PAGE * 0.6:
            params["font_size"] = max(14, params.get("font_size", 18) - 2)

        return params


# Module-level singleton
layout_engine = LayoutEngine()
