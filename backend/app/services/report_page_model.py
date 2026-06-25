"""
ReportPageModel —— 统一报告页面模型

PPT/PDF/Word 三种格式共享同一份页面描述，保证：
- 页面结构一致：PPT 第 N 页 = PDF 第 N 页 = Word 第 N 页
- 布局约束内建：文字区/图片区高度限制，防止溢出和遮挡
- 图片 base64 内嵌：不出现链接或占位图

数据流：
    ReporterAgent Markdown → MarkdownPageParser → ReportPageModel
    → QualityValidator → PPTPageRenderer / PDFPageRenderer / DOCXPageRenderer
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── 页面物理常量（标准 16:9 幻灯片） ──

SLIDE_WIDTH_INCH = 13.333
SLIDE_HEIGHT_INCH = 7.5
MARGIN_LEFT_INCH = 0.5
MARGIN_RIGHT_INCH = 0.5
MARGIN_TOP_INCH = 0.3
MARGIN_BOTTOM_INCH = 0.3

USABLE_WIDTH = SLIDE_WIDTH_INCH - MARGIN_LEFT_INCH - MARGIN_RIGHT_INCH   # 12.333
USABLE_HEIGHT = SLIDE_HEIGHT_INCH - MARGIN_TOP_INCH - MARGIN_BOTTOM_INCH  # 6.9

# 布局限制
MAX_CHARS_PER_PAGE = 800
MAX_IMAGES_PER_PAGE = 3
TEXT_AREA_MAX_HEIGHT = 3.0   # text_top 布局中文字区最大高度
IMAGE_AREA_MAX_HEIGHT = 3.5  # text_top 布局中图片区最大高度
TEXT_LEFT_MAX_WIDTH = 5.5    # text_left 布局中文字区最大宽度
IMAGE_RIGHT_MAX_WIDTH = 5.5  # text_left 布局中图片区最大宽度

# 图片尺寸约束
MIN_IMAGE_WIDTH_PX = 200
MIN_IMAGE_HEIGHT_PX = 150
PLACEHOLDER_VARIANCE_THRESHOLD = 30  # 像素方差低于此值视为纯色占位图

# 字体颜色
DEFAULT_TEXT_COLOR = "#333333"
DEFAULT_TITLE_COLOR = "#1F3A5F"
WHITE_COLOR = "#FFFFFF"
DEFAULT_BG_COLOR = "#FFFFFF"

# WCAG AA 对比度阈值
CONTRAST_RATIO_BODY_MIN = 4.5
CONTRAST_RATIO_TITLE_MIN = 3.0


# ── 数据类 ──


@dataclass
class TextBlock:
    """文本块 —— 一个段落或标题"""
    text: str
    style: str = "body"           # title / subtitle / body / bullet / caption
    font_size: int = 14           # Pt
    bold: bool = False
    color: str = DEFAULT_TEXT_COLOR
    alignment: str = "left"       # left / center / right
    max_lines: int = 0            # 0=不限制

    @property
    def char_count(self) -> int:
        """估算中文字符数（英文/数字按 0.6 折算）"""
        total = 0
        for ch in self.text:
            if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f':
                total += 1
            elif ch.isascii():
                total += 0.6
            else:
                total += 1
        return int(total)

    @property
    def estimated_lines(self) -> int:
        """估算该文本块在 12.3 inch 宽文本框中的行数"""
        if not self.text:
            return 0
        # 每个中文字符宽度 ≈ 字号 × 1.0 点, 每英寸 72 点
        char_width_pt = self.font_size * 1.0
        chars_per_line = max(1, int(USABLE_WIDTH * 72 / char_width_pt))
        return max(1, (self.char_count + chars_per_line - 1) // chars_per_line)


@dataclass
class ImageBlock:
    """图片块"""
    base64: str                   # base64 编码的图片数据
    alt: str = ""                 # 替代文本
    width_ratio: float = 0.85     # 占页面宽度比例 (0~1)
    max_height_inch: float = 3.0  # 最大高度（英寸）
    position: str = "bottom"      # bottom / top / left / right / standalone


@dataclass
class TableBlock:
    """表格块 —— 将 Markdown 表格转换为 PPT 表格"""
    headers: List[str] = field(default_factory=list)  # 表头
    rows: List[List[str]] = field(default_factory=list)  # 数据行（每行是一个 list）
    caption: str = ""  # 表格标题/说明


@dataclass
class PageModel:
    """单页模型 —— PPT/PDF/Word 共享的最小单元

    html-ppt 语义字段（Phase 1 新增，全部 optional，保持向后兼容）：
    - layout: 31 个 html-ppt layouts 之一（cover/toc/section/bullets/kpi_grid/...）
    - animations: data-anim 值列表（fade-up / fade-left / rise-in / counter-up / ...）
    - data_fx: canvas FX 标识（knowledge-graph / particle-burst / confetti-cannon / ...）
    - notes: 150-300 字演讲者逐字稿
    - kpi_metrics: KPI 卡片数据（[{label, value, raw_value, change, trend, unit}]）
    - kicker: 章节小标/眉头
    """
    page_type: str                # cover / toc / section / content / picture / summary
    title: str = ""
    subtitle: str = ""
    kicker: str = ""              # 章节小标（封面/章节页眉头用）
    text_blocks: List[TextBlock] = field(default_factory=list)
    images: List[ImageBlock] = field(default_factory=list)
    tables: List[TableBlock] = field(default_factory=list)
    kpi_metrics: List[Dict[str, Any]] = field(default_factory=list)  # KPI 卡片数据
    animations: List[str] = field(default_factory=list)              # data-anim 值列表
    data_fx: str = ""                                                # canvas FX 标识
    notes: str = ""                                                  # 演讲者逐字稿
    layout_hint: str = "text_top"  # text_top / text_left / image_only / text_only
    bg_color: str = DEFAULT_BG_COLOR
    section_number: int = 0
    # html-ppt layout 名称（与 LayoutType 对齐，缺省由 _choose_layout 决定）
    layout: str = ""

    @property
    def total_chars(self) -> int:
        return sum(tb.char_count for tb in self.text_blocks)

    @property
    def total_lines(self) -> int:
        return sum(tb.estimated_lines for tb in self.text_blocks)

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def has_images(self) -> bool:
        return len(self.images) > 0

    def validate_constraints(self) -> List[str]:
        """自检页面约束，返回违规描述列表"""
        issues: List[str] = []
        if self.total_chars > MAX_CHARS_PER_PAGE:
            issues.append(f"文字溢出: {self.total_chars} > {MAX_CHARS_PER_PAGE} 字符")
        if self.image_count > MAX_IMAGES_PER_PAGE:
            issues.append(f"图片过多: {self.image_count} > {MAX_IMAGES_PER_PAGE}")
        if self.layout_hint == "text_top":
            text_height = self._estimate_text_height()
            img_height = sum(img.max_height_inch for img in self.images)
            if text_height + img_height > USABLE_HEIGHT:
                issues.append(
                    f"text_top 布局溢出: 文字区 {text_height:.1f}\" + "
                    f"图片区 {img_height:.1f}\" > {USABLE_HEIGHT}\""
                )
        return issues

    def _estimate_text_height(self) -> float:
        """估算文字区高度（英寸）"""
        if not self.text_blocks:
            return 0
        line_height_inch = 0.35  # 每行约 0.35 英寸
        return min(self.total_lines * line_height_inch, TEXT_AREA_MAX_HEIGHT)


@dataclass
class ReportPageModel:
    """报告页面模型 —— 一份完整报告的页面描述"""
    title: str
    pages: List[PageModel]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def get_pages_by_type(self, page_type: str) -> List[PageModel]:
        return [p for p in self.pages if p.page_type == page_type]

    def get_section_pages(self, section_number: int) -> List[PageModel]:
        return [p for p in self.pages if p.section_number == section_number]


# ── 工厂方法 ──


def make_cover_page(title: str, subtitle: str = "", bg_color: str = DEFAULT_BG_COLOR) -> PageModel:
    return PageModel(
        page_type="cover",
        title=title,
        subtitle=subtitle,
        text_blocks=[
            TextBlock(text=title, style="title", font_size=32, bold=True,
                      color=DEFAULT_TITLE_COLOR, alignment="center"),
            TextBlock(text=subtitle, style="subtitle", font_size=16,
                      color=DEFAULT_TEXT_COLOR, alignment="center"),
        ],
        layout_hint="text_only",
        bg_color=bg_color,
    )


def make_toc_page(section_titles: List[str], bg_color: str = DEFAULT_BG_COLOR) -> PageModel:
    blocks = [TextBlock(text="目录", style="title", font_size=28, bold=True,
                        color=DEFAULT_TITLE_COLOR)]
    for i, title in enumerate(section_titles, 1):
        blocks.append(TextBlock(
            text=f"{i:02d}. {title}",
            style="body", font_size=18, color=DEFAULT_TEXT_COLOR,
        ))
    return PageModel(
        page_type="toc",
        title="目录",
        text_blocks=blocks,
        layout_hint="text_only",
        bg_color=bg_color,
    )


def make_section_page(section_title: str, section_number: int,
                      bg_color: str = DEFAULT_BG_COLOR) -> PageModel:
    return PageModel(
        page_type="section",
        title=section_title,
        text_blocks=[
            TextBlock(text=f"{section_number:02d}  {section_title}",
                      style="title", font_size=32, bold=True,
                      color=DEFAULT_TITLE_COLOR, alignment="center"),
        ],
        layout_hint="text_only",
        section_number=section_number,
        bg_color=bg_color,
    )


def make_content_page(
    section_title: str,
    section_number: int,
    text_blocks: List[TextBlock],
    images: Optional[List[ImageBlock]] = None,
    tables: Optional[List[TableBlock]] = None,
    page_index: int = 0,
    bg_color: str = DEFAULT_BG_COLOR,
) -> PageModel:
    images = images or []
    tables = tables or []
    title_text = section_title if page_index == 0 else f"{section_title} (续)"
    all_blocks = [
        TextBlock(text=title_text, style="title", font_size=22, bold=True,
                  color=DEFAULT_TITLE_COLOR),
    ] + text_blocks

    layout = "text_top" if images else "text_only"
    return PageModel(
        page_type="content",
        title=title_text,
        text_blocks=all_blocks,
        images=images,
        tables=tables,
        layout_hint=layout,
        section_number=section_number,
        bg_color=bg_color,
    )


def make_picture_page(title: str, images: List[ImageBlock],
                      section_number: int = 0,
                      bg_color: str = DEFAULT_BG_COLOR) -> PageModel:
    return PageModel(
        page_type="picture",
        title=title,
        text_blocks=[
            TextBlock(text=title, style="title", font_size=20, bold=True,
                      color=DEFAULT_TITLE_COLOR),
        ],
        images=images,
        layout_hint="image_only",
        section_number=section_number,
        bg_color=bg_color,
    )


def make_summary_page(text_blocks: List[TextBlock],
                      bg_color: str = DEFAULT_BG_COLOR) -> PageModel:
    return PageModel(
        page_type="summary",
        title="总结与展望",
        text_blocks=[
            TextBlock(text="总结与展望", style="title", font_size=28, bold=True,
                      color=DEFAULT_TITLE_COLOR),
        ] + text_blocks,
        layout_hint="text_only",
        bg_color=bg_color,
    )