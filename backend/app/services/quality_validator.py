"""
QualityValidator —— 报告质量校验与自动修复

在渲染前对 ReportPageModel 进行全面校验，发现问题自动修复。

校验规则：
1. 图片有效性：base64 非空、PIL 可解码、尺寸 ≥ 200×150、非纯色占位图
2. 布局冲突：文字区 + 图片区不重叠，总高度 ≤ 可用高度
3. 文字溢出：估算字数/行数 > 可用空间 → 缩小字号或拆分
4. 对比度：WCAG AA 标准，正文 ≥ 4.5:1，标题 ≥ 3:1
5. 图文比例：连续 2 页以上无图片 → 警告

修复策略（全自动，不阻塞生成）：
- 无效图片 → 移除，降级为关键词卡片
- 占位图 → 移除，降级为关键词卡片
- 布局溢出 → 缩小图片 max_height，调整字号
- 文字溢出 → 缩小字号（最小 11pt），多余文字移到下一页
- 对比度不足 → 深色背景→白色文字，浅色背景→深灰文字
"""

import base64
import io
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.report_page_model import (
    ReportPageModel, PageModel, TextBlock, ImageBlock, TableBlock,
    DEFAULT_TEXT_COLOR, DEFAULT_TITLE_COLOR, WHITE_COLOR,
    DEFAULT_BG_COLOR, USABLE_HEIGHT, TEXT_AREA_MAX_HEIGHT,
    IMAGE_AREA_MAX_HEIGHT, MAX_CHARS_PER_PAGE, MAX_IMAGES_PER_PAGE,
    MIN_IMAGE_WIDTH_PX, MIN_IMAGE_HEIGHT_PX,
    PLACEHOLDER_VARIANCE_THRESHOLD,
    CONTRAST_RATIO_BODY_MIN, CONTRAST_RATIO_TITLE_MIN,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """校验结果"""
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    fixes_applied: List[str] = field(default_factory=list)
    fixed_model: Optional[ReportPageModel] = None


class QualityValidator:
    """报告质量校验器"""

    def __init__(self):
        self._pil_available = self._check_pil()

    @staticmethod
    def _check_pil() -> bool:
        try:
            from PIL import Image as PILImage  # noqa: F401
            return True
        except ImportError:
            logger.warning("PIL not available, image validation will be limited")
            return False

    # ── 公开 API ──

    def validate(self, model: ReportPageModel) -> ValidationResult:
        """对 ReportPageModel 进行全面校验并自动修复

        Args:
            model: 待校验的报告页面模型

        Returns:
            ValidationResult 包含校验结果和修复后的模型
        """
        result = ValidationResult()
        # 深拷贝 pages 以便修复
        fixed_pages = [self._copy_page(p) for p in model.pages]

        # 逐页校验
        for i, page in enumerate(fixed_pages):
            self._validate_page(page, i, result)

        # 全局校验
        self._validate_global(model, fixed_pages, result)

        if result.errors or result.fixes_applied:
            result.passed = len(result.errors) == 0
            result.fixed_model = ReportPageModel(
                title=model.title,
                pages=fixed_pages,
                metadata=dict(model.metadata),
            )
            result.fixed_model.metadata["validation"] = {
                "passed": result.passed,
                "errors": len(result.errors),
                "warnings": len(result.warnings),
                "fixes": result.fixes_applied,
            }
        else:
            result.fixed_model = model

        logger.info(
            "QualityValidator: %d pages, errors=%d, warnings=%d, fixes=%d",
            len(fixed_pages), len(result.errors),
            len(result.warnings), len(result.fixes_applied),
        )
        return result

    # ── 单页校验 ──

    def _validate_page(self, page: PageModel, index: int, result: ValidationResult):
        # 1. 图片有效性
        self._validate_images(page, index, result)

        # 2. 布局冲突
        self._validate_layout(page, index, result)

        # 3. 文字溢出
        self._validate_text_overflow(page, index, result)

        # 4. 对比度
        self._validate_contrast(page, index, result)

    # ── 图片校验 ──

    def _validate_images(self, page: PageModel, index: int, result: ValidationResult):
        valid_images: List[ImageBlock] = []
        for img_idx, img in enumerate(page.images):
            issues = self._check_image(img)

            # 额外检查：渲染尺寸参数是否合理
            if not issues and img.width_ratio < 0.35:
                old_ratio = img.width_ratio
                img.width_ratio = 0.5
                result.warnings.append(
                    f"页{index+1} 图片{img_idx+1}: width_ratio={old_ratio} 过小，"
                    f"自动提升至 {img.width_ratio}"
                )
                result.fixes_applied.append(
                    f"页{index+1} 图片{img_idx+1}: width_ratio {old_ratio} → {img.width_ratio}"
                )
            if not issues and img.max_height_inch < 1.0:
                old_h = img.max_height_inch
                img.max_height_inch = 1.5
                result.warnings.append(
                    f"页{index+1} 图片{img_idx+1}: max_height_inch={old_h} 过小，"
                    f"自动提升至 {img.max_height_inch}"
                )
                result.fixes_applied.append(
                    f"页{index+1} 图片{img_idx+1}: max_height_inch {old_h} → {img.max_height_inch}"
                )

            if issues:
                for issue in issues:
                    result.errors.append(f"页{index+1} 图片{img_idx+1}: {issue}")
                result.fixes_applied.append(
                    f"页{index+1} 图片{img_idx+1}: 移除无效图片，降级为关键词卡片"
                )
                # 不加入 valid_images（移除）
            else:
                valid_images.append(img)
        page.images = valid_images

    def _check_image(self, img: ImageBlock) -> List[str]:
        """检查单张图片，返回问题列表"""
        issues: List[str] = []
        if not img.base64 or not img.base64.strip():
            issues.append("base64 数据为空")
            return issues

        try:
            raw = base64.b64decode(img.base64.strip(), validate=True)
        except Exception as e:
            issues.append(f"base64 解码失败: {e}")
            return issues

        if not self._pil_available:
            return issues  # 无法进一步检查

        try:
            from PIL import Image as PILImage
            buf = io.BytesIO(raw)
            with PILImage.open(buf) as pil_img:
                w, h = pil_img.size
                if w < MIN_IMAGE_WIDTH_PX or h < MIN_IMAGE_HEIGHT_PX:
                    issues.append(f"图片尺寸过小: {w}×{h} (最小 {MIN_IMAGE_WIDTH_PX}×{MIN_IMAGE_HEIGHT_PX})")
                # 检查是否为纯色占位图
                if not issues:
                    if self._is_placeholder(pil_img):
                        issues.append("疑似纯色占位图（像素方差过低）")
        except Exception as e:
            issues.append(f"PIL 无法解码: {e}")

        return issues

    def _is_placeholder(self, pil_img) -> bool:
        """检测是否为纯色占位图（像素方差 < 阈值）"""
        try:
            import numpy as np
            arr = np.array(pil_img.convert("RGB"), dtype=np.float64)
            variance = np.var(arr)
            return variance < PLACEHOLDER_VARIANCE_THRESHOLD
        except ImportError:
            # 无 numpy 时用 PIL 粗略计算
            return self._is_placeholder_pil(pil_img)

    def _is_placeholder_pil(self, pil_img) -> bool:
        """PIL 粗略纯色检测（采样方式）"""
        try:
            small = pil_img.resize((10, 10))
            pixels = list(small.getdata())
            if not pixels:
                return False
            # 计算平均颜色
            if isinstance(pixels[0], int):
                return False  # 无法处理灰度
            avg_r = sum(p[0] for p in pixels) / len(pixels)
            avg_g = sum(p[1] for p in pixels) / len(pixels)
            avg_b = sum(p[2] for p in pixels) / len(pixels)
            # 检查所有像素是否接近平均值
            threshold = 15
            for p in pixels:
                if (abs(p[0] - avg_r) > threshold or
                    abs(p[1] - avg_g) > threshold or
                    abs(p[2] - avg_b) > threshold):
                    return False
            return True
        except Exception:
            return False

    # ── 布局校验 ──

    def _validate_layout(self, page: PageModel, index: int, result: ValidationResult):
        """校验布局是否冲突"""
        if page.layout_hint == "text_top" and page.images:
            text_height = page._estimate_text_height()
            img_height = sum(img.max_height_inch for img in page.images)

            if text_height > TEXT_AREA_MAX_HEIGHT:
                result.warnings.append(
                    f"页{index+1}: 文字区高度 {text_height:.1f}\" > {TEXT_AREA_MAX_HEIGHT}\""
                )
                self._fix_text_overflow(page, index, result)

            if text_height + img_height > USABLE_HEIGHT:
                result.errors.append(
                    f"页{index+1}: text_top 布局溢出 "
                    f"(文字{text_height:.1f}\" + 图片{img_height:.1f}\" > {USABLE_HEIGHT}\")"
                )
                self._fix_layout_overflow(page, index, text_height, img_height, result)

    def _fix_layout_overflow(
        self, page: PageModel, index: int,
        text_height: float, img_height: float, result: ValidationResult,
    ):
        """修复布局溢出：缩小图片高度"""
        available = USABLE_HEIGHT - text_height
        if available <= 0.5:
            # 文字区太大，先缩文字
            self._fix_text_overflow(page, index, result)
            text_height = page._estimate_text_height()
            available = USABLE_HEIGHT - text_height

        if available > 0 and page.images:
            total_ratio = sum(img.max_height_inch for img in page.images)
            if total_ratio > 0:
                scale = available / total_ratio
                for img in page.images:
                    img.max_height_inch = round(img.max_height_inch * scale, 2)
                result.fixes_applied.append(
                    f"页{index+1}: 图片高度缩放至 {scale:.0%}，适配布局"
                )

    # ── 文字溢出校验 ──

    def _validate_text_overflow(self, page: PageModel, index: int, result: ValidationResult):
        """校验文字是否溢出"""
        total_chars = page.total_chars
        if total_chars > MAX_CHARS_PER_PAGE:
            result.errors.append(
                f"页{index+1}: 文字溢出 {total_chars} > {MAX_CHARS_PER_PAGE} 字符"
            )
            self._fix_text_overflow(page, index, result)

    def _fix_text_overflow(self, page: PageModel, index: int, result: ValidationResult):
        """修复文字溢出：缩小字号"""
        overflow = page.total_chars - MAX_CHARS_PER_PAGE
        if overflow <= 0:
            return

        # 按比例缩小所有正文 TextBlock 的字号
        ratio = MAX_CHARS_PER_PAGE / max(page.total_chars, 1)
        min_font = 11
        for tb in page.text_blocks:
            if tb.style in ("body", "bullet", "caption"):
                new_size = max(min_font, int(tb.font_size * ratio))
                if new_size < tb.font_size:
                    tb.font_size = new_size

        result.fixes_applied.append(
            f"页{index+1}: 文字溢出 {overflow} 字符，字号已缩小至 ≥ {min_font}pt"
        )

    # ── 对比度校验 ──

    def _validate_contrast(self, page: PageModel, index: int, result: ValidationResult):
        """校验文字颜色与背景的对比度"""
        bg_rgb = self._hex_to_rgb(page.bg_color)
        if bg_rgb is None:
            return

        for tb in page.text_blocks:
            fg_rgb = self._hex_to_rgb(tb.color)
            if fg_rgb is None:
                continue
            ratio = self._contrast_ratio(fg_rgb, bg_rgb)

            is_title = tb.style in ("title", "subtitle")
            threshold = CONTRAST_RATIO_TITLE_MIN if is_title else CONTRAST_RATIO_BODY_MIN

            if ratio < threshold:
                result.warnings.append(
                    f"页{index+1} \"{tb.text[:20]}...\": "
                    f"对比度 {ratio:.1f} < {threshold} (WCAG AA)"
                )
                # 自动修复
                tb.color = self._fix_color(page.bg_color, is_title)
                result.fixes_applied.append(
                    f"页{index+1}: 文字颜色已自动调整以适配背景"
                )

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> Optional[Tuple[int, int, int]]:
        """#RRGGBB → (R, G, B)"""
        hex_str = hex_color.lstrip('#')
        if len(hex_str) < 6:
            return None
        try:
            return (
                int(hex_str[0:2], 16),
                int(hex_str[2:4], 16),
                int(hex_str[4:6], 16),
            )
        except ValueError:
            return None

    @staticmethod
    def _relative_luminance(rgb: Tuple[int, int, int]) -> float:
        """计算相对亮度（WCAG 公式）"""
        def _channel(c: int) -> float:
            s = c / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
        return 0.2126 * _channel(rgb[0]) + 0.7152 * _channel(rgb[1]) + 0.0722 * _channel(rgb[2])

    @classmethod
    def _contrast_ratio(cls, fg: Tuple[int, int, int], bg: Tuple[int, int, int]) -> float:
        """计算对比度（WCAG 公式）"""
        l1 = cls._relative_luminance(fg)
        l2 = cls._relative_luminance(bg)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    @staticmethod
    def _fix_color(bg_color: str, is_title: bool) -> str:
        """根据背景色自动选择文字颜色"""
        bg_rgb = QualityValidator._hex_to_rgb(bg_color)
        if bg_rgb is None:
            return DEFAULT_TITLE_COLOR if is_title else DEFAULT_TEXT_COLOR

        # 简单亮度判断
        luminance = (bg_rgb[0] * 299 + bg_rgb[1] * 587 + bg_rgb[2] * 114) / 1000
        if luminance < 128:
            return WHITE_COLOR  # 深色背景 → 白色文字
        return DEFAULT_TITLE_COLOR if is_title else DEFAULT_TEXT_COLOR

    # ── 全局校验 ──

    def _validate_global(
        self,
        model: ReportPageModel,
        fixed_pages: List[PageModel],
        result: ValidationResult,
    ):
        """全局校验：图文比例"""
        consecutive_no_image = 0
        for i, page in enumerate(fixed_pages):
            if page.page_type in ("content", "section") and not page.has_images:
                consecutive_no_image += 1
            else:
                consecutive_no_image = 0

            if consecutive_no_image >= 2:
                result.warnings.append(
                    f"页{i+1}: 连续 {consecutive_no_image} 页无图片，建议增加配图"
                )

    # ── 辅助 ──

    @staticmethod
    def _copy_page(page: PageModel) -> PageModel:
        """深拷贝 PageModel"""
        return PageModel(
            page_type=page.page_type,
            title=page.title,
            subtitle=page.subtitle,
            text_blocks=[
                TextBlock(
                    text=tb.text, style=tb.style, font_size=tb.font_size,
                    bold=tb.bold, color=tb.color, alignment=tb.alignment,
                    max_lines=tb.max_lines,
                )
                for tb in page.text_blocks
            ],
            images=[
                ImageBlock(
                    base64=img.base64, alt=img.alt,
                    width_ratio=img.width_ratio,
                    max_height_inch=img.max_height_inch,
                    position=img.position,
                )
                for img in page.images
            ],
            tables=[
                TableBlock(
                    headers=list(tbl.headers),
                    rows=[list(row) for row in tbl.rows],
                    caption=tbl.caption,
                )
                for tbl in page.tables
            ],
            layout_hint=page.layout_hint,
            bg_color=page.bg_color,
            section_number=page.section_number,
        )