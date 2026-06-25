"""
End-to-end integration test for the HTML report pipeline.

Tests the full flow: ThemeSelector -> HTMLReportGenerator -> QualityValidator
covering rule-based theme selection, HTML structure compliance, multi-slide
generation, and edge cases (empty insights, missing dimensions).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.theme_selector import ThemeSelector, THEME_CATEGORIES, DEFAULT_THEME
from app.services.html_report_generator import (
    HTMLReportGenerator,
    HTMLPageModel,
    HTMLTextBlock,
    HTMLImageBlock,
    LayoutType,
    quick_generate,
)
from app.services.quality_validator import QualityValidator
from app.services.report_page_model import (
    ReportPageModel,
    PageModel,
    TextBlock,
    ImageBlock,
    TableBlock,
)
from app.schemas.agent import (
    AnalyzerOutput,
    Insight,
    ReporterOutput,
    DEFAULT_DIMENSIONS,
)


# ============================================================
# Helpers
# ============================================================

def _build_report_page_model(
    title: str = "Test Report",
    pages: list = None,
) -> ReportPageModel:
    """Build a minimal ReportPageModel for validator tests."""
    if pages is None:
        pages = [
            PageModel(
                page_type="cover",
                title=title,
                text_blocks=[
                    TextBlock(text=title, style="title", font_size=32, bold=True),
                    TextBlock(text="Subtitle", style="subtitle", font_size=16),
                ],
                layout_hint="text_only",
            ),
            PageModel(
                page_type="content",
                title="Analysis",
                text_blocks=[
                    TextBlock(text="Analysis body text goes here.", style="body", font_size=14),
                ],
                layout_hint="text_only",
            ),
        ]
    return ReportPageModel(title=title, pages=pages)


def _build_html_pages_for_report(topic: str, num_sections: int = 3) -> list:
    """Build HTMLPageModel list simulating a realistic report."""
    pages = [
        HTMLPageModel(
            title=topic,
            layout=LayoutType.COVER,
            kicker="Market Insight Report",
            text_blocks=[HTMLTextBlock(text="Executive summary for this topic.")],
        ),
        HTMLPageModel(
            title="Table of Contents",
            layout=LayoutType.TOC,
            text_blocks=[HTMLTextBlock(text=f"Section {i+1}") for i in range(num_sections)],
        ),
    ]
    for i in range(num_sections):
        pages.append(HTMLPageModel(
            title=f"Section {i+1}: Dimension Analysis",
            layout=LayoutType.CONTENT,
            text_blocks=[HTMLTextBlock(text=f"Analysis content for section {i+1}.")],
        ))
    pages.append(
        HTMLPageModel(
            title="Thank You",
            layout=LayoutType.THANKS,
            text_blocks=[HTMLTextBlock(text="End of report.")],
        )
    )
    return pages


# ============================================================
# 1. ThemeSelector tests
# ============================================================

def test_theme_selector_business_formal():
    sel = ThemeSelector()
    assert sel.select_theme("企业董事会战略汇报") == "corporate-clean"
    assert sel.select_theme("B2B Sales Analysis") == "corporate-clean"
    assert sel.select_theme("金融保险行业报告") == "corporate-clean"


def test_theme_selector_tech():
    sel = ThemeSelector()
    assert sel.select_theme("Kubernetes微服务架构技术分享") == "tokyo-night"
    assert sel.select_theme("DevOps Cloud Infrastructure Report") == "tokyo-night"


def test_theme_selector_consumer():
    sel = ThemeSelector()
    assert sel.select_theme("小红书种草好物推荐") == "xiaohongshu-white"
    assert sel.select_theme("Consumer Product Launch Plan") == "xiaohongshu-white"


def test_theme_selector_financial():
    sel = ThemeSelector()
    assert sel.select_theme("2024年投资市场财务分析") == "corporate-clean"
    assert sel.select_theme("Financial Report Q3 2024") == "corporate-clean"


def test_theme_selector_academic():
    sel = ThemeSelector()
    assert sel.select_theme("学术论文研究方法论分享") == "academic-paper"
    assert sel.select_theme("Research Paper Conference") == "academic-paper"


def test_theme_selector_default_fallback():
    sel = ThemeSelector()
    assert sel.select_theme("random unrelated topic xyz") == DEFAULT_THEME


def test_theme_selector_empty_input():
    sel = ThemeSelector()
    assert sel.select_theme("") == DEFAULT_THEME
    assert sel.select_theme("  ") == DEFAULT_THEME


def test_theme_selector_content_boost():
    sel = ThemeSelector()
    topic = "Report"
    content = "Kubernetes Docker microservices architecture"
    theme = sel.select_theme(topic, content=content)
    assert theme == "tokyo-night", f"Expected tokyo-night with content boost, got {theme}"


def test_theme_selector_categories_filter():
    sel = ThemeSelector()
    theme = sel.select_theme(
        "技术分享", categories=["consumer_product", "academic_report"]
    )
    assert theme == DEFAULT_THEME, "Should not match tech when filtered out"


# ============================================================
# 2. HTMLReportGenerator structure tests
# ============================================================

def test_generator_produces_valid_html():
    gen = HTMLReportGenerator()
    pages = _build_html_pages_for_report("AI Market Insight")
    html = gen.generate(pages)

    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html
    assert "<head>" in html
    assert "<body" in html
    assert "</body>" in html


def test_generator_includes_required_assets():
    gen = HTMLReportGenerator()
    html = gen.generate(_build_html_pages_for_report("Test"))

    assert "runtime.js" in html, "Missing runtime.js"
    assert "fx-runtime.js" in html, "Missing fx-runtime.js"
    assert "base.css" in html, "Missing base.css"
    assert "fonts.css" in html, "Missing fonts.css"
    assert "animations.css" in html, "Missing animations.css"


def test_generator_includes_theme_link():
    gen = HTMLReportGenerator(theme="tokyo-night")
    html = gen.generate(_build_html_pages_for_report("Test"))

    assert 'data-theme="tokyo-night"' in html
    assert 'themes/tokyo-night.css' in html
    assert 'id="theme-link"' in html


def test_generator_slide_count():
    gen = HTMLReportGenerator()
    pages = _build_html_pages_for_report("Test Topic", num_sections=5)
    html = gen.generate(pages)

    slide_count = len(re.findall(r'<section class="slide', html))
    expected = 2 + 5 + 1  # cover + toc + 5 sections + thanks
    assert slide_count == expected, f"Expected {expected} slides, got {slide_count}"


def test_generator_slide_number_data_attributes():
    gen = HTMLReportGenerator()
    pages = _build_html_pages_for_report("Test", num_sections=3)
    html = gen.generate(pages)

    nums = re.findall(
        r'<span class="slide-number" data-current="(\d+)" data-total="(\d+)">',
        html,
    )
    total = len(pages)
    assert len(nums) == total, f"Expected {total} slide-number elements, got {len(nums)}"
    assert nums[0][0] == "1"
    assert nums[-1][0] == str(total)
    for _, t in nums:
        assert t == str(total), f"data-total mismatch: {t} != {total}"


def test_generator_first_slide_active():
    gen = HTMLReportGenerator()
    html = gen.generate(_build_html_pages_for_report("Test"))
    slides = re.findall(r'<section class="([^"]*)"', html)
    assert slides[0].startswith("slide is-active"), f"First slide: {slides[0]}"
    for s in slides[1:]:
        assert "is-active" not in s, f"Non-first slide has is-active: {s}"


def test_generator_data_themes_on_body():
    gen = HTMLReportGenerator()
    html = gen.generate(_build_html_pages_for_report("Test"))
    match = re.search(r'<body[^>]*data-themes="([^"]*)"', html)
    assert match, "data-themes not found on body"
    themes = match.group(1).split(",")
    assert len(themes) > 0
    assert "minimal-white" in themes


def test_generator_notes_div():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(title="Slide One", layout=LayoutType.CONTENT,
                      text_blocks=[HTMLTextBlock(text="Hello")]),
        HTMLPageModel(title="Slide Two", layout=LayoutType.BULLETS,
                      text_blocks=[HTMLTextBlock(text="Point")]),
    ]
    html = gen.generate(pages)
    notes = re.findall(r'class="notes"', html)
    assert len(notes) == 2


# ============================================================
# 3. Multi-slide generation tests
# ============================================================

def test_all_layout_types_render():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(title="Cover", layout=LayoutType.COVER,
                      text_blocks=[HTMLTextBlock(text="Sub")]),
        HTMLPageModel(title="TOC", layout=LayoutType.TOC,
                      text_blocks=[HTMLTextBlock(text="Item")]),
        HTMLPageModel(title="Section", layout=LayoutType.SECTION),
        HTMLPageModel(title="Bullets", layout=LayoutType.BULLETS,
                      text_blocks=[HTMLTextBlock(text="P1"), HTMLTextBlock(text="P2")]),
        HTMLPageModel(title="KPIs", layout=LayoutType.KPI_GRID,
                      kpi_metrics=[{"value": "10", "label": "M", "raw_value": "10"}]),
        HTMLPageModel(title="Two Col", layout=LayoutType.TWO_COLUMN,
                      text_blocks=[HTMLTextBlock(text="A"), HTMLTextBlock(text="B")]),
        HTMLPageModel(title="Three Col", layout=LayoutType.THREE_COLUMN,
                      text_blocks=[HTMLTextBlock(text="X"), HTMLTextBlock(text="Y"),
                                   HTMLTextBlock(text="Z")]),
        HTMLPageModel(title="Table", layout=LayoutType.TABLE,
                      table_data={"headers": ["A"], "rows": [["1"]]}),
        HTMLPageModel(title="Image Hero", layout=LayoutType.IMAGE_HERO,
                      image_blocks=[HTMLImageBlock(url="img.png", caption="Pic")]),
        HTMLPageModel(title="Image Grid", layout=LayoutType.IMAGE_GRID,
                      image_blocks=[HTMLImageBlock(url="a.png", caption="A")]),
        HTMLPageModel(title="Stat", layout=LayoutType.STAT_HIGHLIGHT,
                      kpi_metrics=[{"value": "99%", "label": "Rate", "raw_value": "99"}]),
        HTMLPageModel(title="Content", layout=LayoutType.CONTENT,
                      text_blocks=[HTMLTextBlock(text="Body text")]),
        HTMLPageModel(title="Thanks", layout=LayoutType.THANKS),
    ]
    html = gen.generate(pages)
    slides = re.findall(r'<section class="slide', html)
    assert len(slides) == 13, f"Expected 13 slides, got {len(slides)}"
    assert len(html) > 3000, "Generated HTML should be substantial"


def test_quick_generate_function():
    sections = [
        {"title": "Overview", "content": "Market overview text"},
        {"title": "Analysis", "content": "Deep analysis text"},
    ]
    html = quick_generate("Market Report", sections, theme="dracula")
    assert 'data-theme="dracula"' in html
    slide_count = len(re.findall(r'<section class="slide', html))
    assert slide_count >= 3, "Should have cover + toc + section slides"


# ============================================================
# 4. Edge cases
# ============================================================

def test_empty_text_blocks():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(title="Empty", layout=LayoutType.CONTENT),
        HTMLPageModel(title="Also Empty", layout=LayoutType.BULLETS),
    ]
    html = gen.generate(pages)
    assert len(html) > 500
    slides = re.findall(r'<section class="slide', html)
    assert len(slides) == 2


def test_empty_image_blocks():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(title="No Images", layout=LayoutType.IMAGE_HERO),
        HTMLPageModel(title="No Grid", layout=LayoutType.IMAGE_GRID),
    ]
    html = gen.generate(pages)
    assert len(html) > 500


def test_empty_table_data():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(title="No Table", layout=LayoutType.TABLE),
    ]
    html = gen.generate(pages)
    assert "No Table" in html


def test_empty_chart_data():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(title="No Chart", layout=LayoutType.CHART_BAR),
    ]
    html = gen.generate(pages)
    assert "No Chart" in html


def test_missing_kpi_metrics_falls_back():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(title="No KPI", layout=LayoutType.KPI_GRID),
        HTMLPageModel(title="No Stat", layout=LayoutType.STAT_HIGHLIGHT),
    ]
    html = gen.generate(pages)
    slides = re.findall(r'<section class="slide', html)
    assert len(slides) == 2


def test_special_characters_escaped():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="<script>alert('xss')</script>",
            layout=LayoutType.CONTENT,
            text_blocks=[HTMLTextBlock(text="Content with <b>bold</b> & ampersand")],
        ),
    ]
    html = gen.generate(pages)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_single_slide_deck():
    gen = HTMLReportGenerator()
    pages = [HTMLPageModel(title="Only", layout=LayoutType.CONTENT)]
    html = gen.generate(pages)
    slides = re.findall(r'<section class="slide is-active"', html)
    assert len(slides) == 1
    assert 'data-total="1"' in html


# ============================================================
# 5. QualityValidator integration
# ============================================================

def test_validator_passes_clean_model():
    validator = QualityValidator()
    model = _build_report_page_model()
    result = validator.validate(model)
    assert result.fixed_model is not None


def test_validator_handles_empty_pages():
    validator = QualityValidator()
    model = _build_report_page_model(pages=[])
    result = validator.validate(model)
    assert result.fixed_model is not None
    assert result.fixed_model.page_count == 0


def test_validator_auto_fixes_raw_base64():
    validator = QualityValidator()
    import base64
    raw_b64 = base64.b64encode(b"fake png data").decode()
    model = _build_report_page_model(pages=[
        PageModel(
            page_type="content",
            title="Img",
            images=[ImageBlock(base64=raw_b64, alt="test")],
            layout_hint="text_only",
        ),
    ])
    result = validator.validate(model)
    assert result.fixed_model is not None
    # The raw base64 should be auto-wrapped with data:image prefix
    if result.fixed_model.pages[0].images:
        assert result.fixed_model.pages[0].images[0].base64.startswith("data:image")


# ============================================================
# 6. Schema integration
# ============================================================

def test_analyzer_output_insights():
    output = AnalyzerOutput(
        task_id="t1",
        success=True,
        summary="Test summary",
        insights=[
            Insight(conclusion="Insight 1", dimension="宏观"),
            Insight(conclusion="Insight 2", dimension="行业"),
        ],
    )
    assert len(output.insights) == 2
    assert output.insights[0].dimension == "宏观"


def test_default_dimensions_available():
    assert len(DEFAULT_DIMENSIONS) >= 4
    assert "宏观经济环境" in DEFAULT_DIMENSIONS


def test_reporter_output_html_content():
    output = ReporterOutput(
        task_id="t1",
        success=True,
        markdown_report="# Report",
        html_content="<html>...</html>",
        theme="tokyo-night",
    )
    assert output.html_content == "<html>...</html>"
    assert output.theme == "tokyo-night"


# ============================================================
# 7. Full pipeline: ThemeSelector -> HTMLReportGenerator
# ============================================================

def test_full_pipeline_theme_to_html():
    sel = ThemeSelector()
    topic = "2024年AI芯片市场投资财务分析"
    theme = sel.select_theme(topic)
    assert theme == "corporate-clean"

    gen = HTMLReportGenerator(theme=theme)
    pages = _build_html_pages_for_report(topic, num_sections=3)
    html = gen.generate(pages)

    assert 'data-theme="corporate-clean"' in html
    assert "runtime.js" in html
    slide_count = len(re.findall(r'<section class="slide', html))
    assert slide_count == 6  # cover + toc + 3 sections + thanks


def test_full_pipeline_tech_report():
    sel = ThemeSelector()
    topic = "Kubernetes微服务架构技术分享"
    theme = sel.select_theme(topic)
    gen = HTMLReportGenerator(theme=theme)
    pages = _build_html_pages_for_report(topic, num_sections=2)
    html = gen.generate(pages)

    assert 'data-theme="tokyo-night"' in html
    slide_count = len(re.findall(r'<section class="slide', html))
    assert slide_count == 5  # cover + toc + 2 sections + thanks


# ============================================================
# Main
# ============================================================

ALL_TESTS = [
    test_theme_selector_business_formal,
    test_theme_selector_tech,
    test_theme_selector_consumer,
    test_theme_selector_financial,
    test_theme_selector_academic,
    test_theme_selector_default_fallback,
    test_theme_selector_empty_input,
    test_theme_selector_content_boost,
    test_theme_selector_categories_filter,
    test_generator_produces_valid_html,
    test_generator_includes_required_assets,
    test_generator_includes_theme_link,
    test_generator_slide_count,
    test_generator_slide_number_data_attributes,
    test_generator_first_slide_active,
    test_generator_data_themes_on_body,
    test_generator_notes_div,
    test_all_layout_types_render,
    test_quick_generate_function,
    test_empty_text_blocks,
    test_empty_image_blocks,
    test_empty_table_data,
    test_empty_chart_data,
    test_missing_kpi_metrics_falls_back,
    test_special_characters_escaped,
    test_single_slide_deck,
    test_validator_passes_clean_model,
    test_validator_handles_empty_pages,
    test_validator_auto_fixes_raw_base64,
    test_analyzer_output_insights,
    test_default_dimensions_available,
    test_reporter_output_html_content,
    test_full_pipeline_theme_to_html,
    test_full_pipeline_tech_report,
]


def main():
    passed = 0
    failed = 0
    errors = []

    for test_fn in ALL_TESTS:
        try:
            test_fn()
            print(f"  PASS: {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            errors.append((test_fn.__name__, e))
            failed += 1

    print(f"\n{'='*60}")
    print(f"E2E Report Pipeline Test Results: {passed} passed, {failed} failed, {len(ALL_TESTS)} total")
    print(f"{'='*60}")

    if failed:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
        sys.exit(1)

    print("All tests passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()
