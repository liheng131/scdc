"""Tests for QualityValidator service."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import base64
from io import BytesIO

from app.services.quality_validator import QualityValidator, ValidationResult
from app.services.report_page_model import (
    ReportPageModel, PageModel, TextBlock, ImageBlock,
    DEFAULT_TEXT_COLOR, DEFAULT_TITLE_COLOR, WHITE_COLOR,
    MIN_IMAGE_WIDTH_PX, MIN_IMAGE_HEIGHT_PX,
)

from PIL import Image as PILImage


def _make_tiny_png(width: int = 100, height: int = 80) -> str:
    """Create a small valid PNG as base64 (with data:image prefix)."""
    img = PILImage.new("RGB", (width, height), (200, 100, 50))
    buf = BytesIO()
    img.save(buf, format="PNG")
    raw = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{raw}"


def _make_large_png() -> str:
    """Create a 300x200 PNG with some color variation."""
    img = PILImage.new("RGB", (300, 200), (100, 150, 200))
    for x in range(50, 250):
        for y in range(50, 150):
            img.putpixel((x, y), (50, 100, 150))
    buf = BytesIO()
    img.save(buf, format="PNG")
    raw = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{raw}"


def _make_uniform_png() -> str:
    """Create a uniform-color PNG (placeholder)."""
    img = PILImage.new("RGB", (300, 200), (128, 128, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    raw = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{raw}"


def test_validator_init():
    v = QualityValidator()
    assert v is not None


def test_validation_result_structure():
    r = ValidationResult()
    assert r.passed is True
    assert r.errors == []
    assert r.warnings == []
    assert r.fixes_applied == []
    assert r.fixed_model is None


def test_valid_page_passes():
    v = QualityValidator()
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[
            TextBlock(text="Hello World", style="body", color="#333333"),
        ],
        images=[],
        bg_color="#FFFFFF",
    )
    model = ReportPageModel(title="Report", pages=[page])
    result = v.validate(model)
    assert result.passed is True
    assert result.fixed_model is not None


def test_empty_image_removal():
    v = QualityValidator()
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[TextBlock(text="Body", style="body")],
        images=[ImageBlock(base64="")],
    )
    model = ReportPageModel(title="Report", pages=[page])
    result = v.validate(model)
    assert len(result.fixed_model.pages[0].images) == 0
    assert any("base64 数据为空" in e for e in result.errors)


def test_small_image_removal():
    v = QualityValidator()
    b64 = _make_tiny_png(50, 40)
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[TextBlock(text="Body", style="body")],
        images=[ImageBlock(base64=b64)],
    )
    model = ReportPageModel(title="R", pages=[page])
    result = v.validate(model)
    assert len(result.fixed_model.pages[0].images) == 0
    assert any("图片尺寸过小" in e for e in result.errors)


def test_valid_image_kept():
    v = QualityValidator()
    b64 = _make_large_png()
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[TextBlock(text="Body", style="body")],
        images=[ImageBlock(base64=b64)],
    )
    model = ReportPageModel(title="R", pages=[page])
    result = v.validate(model)
    assert len(result.fixed_model.pages[0].images) == 1


def test_raw_base64_auto_fix():
    v = QualityValidator()
    b64 = _make_large_png()
    raw = b64.split(",", 1)[1]
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[TextBlock(text="Body", style="body")],
        images=[ImageBlock(base64=raw)],
    )
    model = ReportPageModel(title="R", pages=[page])
    result = v.validate(model)
    assert any("raw base64 自动包装" in f for f in result.fixes_applied)


def test_placeholder_image_removal():
    v = QualityValidator()
    b64 = _make_uniform_png()
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[TextBlock(text="Body", style="body")],
        images=[ImageBlock(base64=b64)],
    )
    model = ReportPageModel(title="R", pages=[page])
    result = v.validate(model)
    assert len(result.fixed_model.pages[0].images) == 0
    assert any("占位图" in e for e in result.errors)


def test_contrast_ratio_calculation():
    v = QualityValidator()
    white = (255, 255, 255)
    black = (0, 0, 0)
    ratio = v._contrast_ratio(white, black)
    assert abs(ratio - 21.0) < 0.5


def test_low_contrast_auto_fix():
    v = QualityValidator()
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[
            TextBlock(text="Low contrast text", style="body", color="#DDDDDD"),
        ],
        bg_color="#FFFFFF",
    )
    model = ReportPageModel(title="R", pages=[page])
    result = v.validate(model)
    assert any("对比度" in w for w in result.warnings)
    assert any("文字颜色" in f for f in result.fixes_applied)
    fixed_tb = result.fixed_model.pages[0].text_blocks[0]
    assert fixed_tb.color != "#DDDDDD"


def test_title_low_contrast_auto_fix():
    v = QualityValidator()
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[
            TextBlock(text="Title", style="title", color="#E0E0E0"),
        ],
        bg_color="#FFFFFF",
    )
    model = ReportPageModel(title="R", pages=[page])
    result = v.validate(model)
    assert any("对比度" in w for w in result.warnings)


def test_hex_to_rgb():
    assert QualityValidator._hex_to_rgb("#FF0000") == (255, 0, 0)
    assert QualityValidator._hex_to_rgb("00FF00") == (0, 255, 0)
    assert QualityValidator._hex_to_rgb("invalid") is None
    assert QualityValidator._hex_to_rgb("#FFF") is None


def test_relative_luminance():
    assert QualityValidator._relative_luminance((0, 0, 0)) == 0.0
    lum = QualityValidator._relative_luminance((255, 255, 255))
    assert abs(lum - 1.0) < 0.01


def test_copy_page_preserves_data():
    page = PageModel(
        page_type="content",
        title="T",
        text_blocks=[TextBlock(text="X", style="body")],
        images=[ImageBlock(base64="abc")],
    )
    copied = QualityValidator._copy_page(page)
    assert copied.title == "T"
    assert copied.text_blocks[0].text == "X"
    assert copied.images[0].base64 == "abc"
    copied.text_blocks[0].text = "Y"
    assert page.text_blocks[0].text == "X"


def test_full_flow_with_errors_and_fixes():
    v = QualityValidator()
    b64 = _make_large_png()
    page = PageModel(
        page_type="content",
        title="Test",
        text_blocks=[
            TextBlock(text="Good contrast body", style="body", color="#333333"),
            TextBlock(text="Low contrast subtitle", style="subtitle", color="#DDDDDD"),
        ],
        images=[
            ImageBlock(base64=""),
            ImageBlock(base64=b64),
        ],
        bg_color="#FFFFFF",
    )
    model = ReportPageModel(title="R", pages=[page])
    result = v.validate(model)
    fixed = result.fixed_model
    assert len(fixed.pages[0].images) == 1
    assert fixed is not None
    assert fixed.metadata["validation"]["errors"] > 0
    assert len(result.fixes_applied) > 0


if __name__ == "__main__":
    test_validator_init()
    test_validation_result_structure()
    test_valid_page_passes()
    test_empty_image_removal()
    test_small_image_removal()
    test_valid_image_kept()
    test_raw_base64_auto_fix()
    test_placeholder_image_removal()
    test_contrast_ratio_calculation()
    test_low_contrast_auto_fix()
    test_title_low_contrast_auto_fix()
    test_hex_to_rgb()
    test_relative_luminance()
    test_copy_page_preserves_data()
    test_full_flow_with_errors_and_fixes()
    print("All tests passed!")
