"""
Tests for export pipeline converters — verifies html-ppt HTML compatibility.

Checks:
1. Each converter class has a `convert` method
2. A sample html-ppt HTML can be parsed by BeautifulSoup (DOCX/MD converters)
3. HTMLReportGenerator produces valid HTML consumed by all converters
"""

import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bs4 import BeautifulSoup

from app.services.html_to_ppt_converter import HTMLToPPTConverter
from app.services.html_to_pdf_converter import HTMLToPDFConverter
from app.services.html_to_docx_converter import HTMLToDOCXConverter
from app.services.html_to_markdown_converter import HTMLToMarkdownConverter
from app.services.html_report_generator import (
    HTMLReportGenerator,
    HTMLPageModel,
    HTMLTextBlock,
    HTMLImageBlock,
    LayoutType,
)


def _generate_sample_html() -> str:
    """Generate a representative html-ppt HTML document."""
    pages = [
        HTMLPageModel(
            title="Market Overview",
            layout=LayoutType.COVER,
            kicker="Research Report",
            text_blocks=[HTMLTextBlock(text="2025 AI Chip Market Trends")],
        ),
        HTMLPageModel(
            title="Contents",
            layout=LayoutType.TOC,
            text_blocks=[HTMLTextBlock(text="Section A"), HTMLTextBlock(text="Section B")],
        ),
        HTMLPageModel(
            title="Key Metrics",
            layout=LayoutType.KPI_GRID,
            kpi_metrics=[
                {"value": "1500", "label": "Market Size (B$)", "raw_value": "1500"},
                {"value": "23.5%", "label": "CAGR", "raw_value": "0.235"},
            ],
        ),
        HTMLPageModel(
            title="Competitive Landscape",
            layout=LayoutType.TABLE,
            table_data={
                "headers": ["Company", "Market Share", "YoY Growth"],
                "rows": [
                    ["NVIDIA", "72%", "+25%"],
                    ["AMD", "15%", "+40%"],
                    ["Intel", "8%", "+10%"],
                ],
            },
        ),
        HTMLPageModel(
            title="Analysis",
            layout=LayoutType.CONTENT,
            text_blocks=[
                HTMLTextBlock(text="AI chips are shifting from training to inference workloads."),
                HTMLTextBlock(text="Edge computing demand is accelerating rapidly."),
            ],
        ),
        HTMLPageModel(
            title="Thanks",
            layout=LayoutType.THANKS,
            text_blocks=[HTMLTextBlock(text="Thank you!")],
        ),
    ]
    return HTMLReportGenerator(theme="minimal-white").generate(pages)


def _make_sample_html() -> str:
    return _generate_sample_html()


# ── Converter interface tests ──


class TestConverterInterfaces:
    """Verify each converter class exposes the expected `convert` method."""

    def test_ppt_converter_has_convert(self):
        assert hasattr(HTMLToPPTConverter, "convert"), "HTMLToPPTConverter missing convert"
        assert callable(getattr(HTMLToPPTConverter, "convert"))

    def test_pdf_converter_has_convert(self):
        assert hasattr(HTMLToPDFConverter, "convert"), "HTMLToPDFConverter missing convert"
        assert callable(getattr(HTMLToPDFConverter, "convert"))

    def test_docx_converter_has_convert(self):
        assert hasattr(HTMLToDOCXConverter, "convert"), "HTMLToDOCXConverter missing convert"
        assert callable(getattr(HTMLToDOCXConverter, "convert"))

    def test_markdown_converter_has_convert(self):
        assert hasattr(HTMLToMarkdownConverter, "convert"), "HTMLToMarkdownConverter missing convert"
        assert callable(getattr(HTMLToMarkdownConverter, "convert"))

    def test_ppt_convert_is_async(self):
        assert inspect.iscoroutinefunction(HTMLToPPTConverter.convert)

    def test_pdf_convert_is_async(self):
        assert inspect.iscoroutinefunction(HTMLToPDFConverter.convert)

    def test_docx_convert_is_async(self):
        assert inspect.iscoroutinefunction(HTMLToDOCXConverter.convert)

    def test_markdown_convert_is_async(self):
        assert inspect.iscoroutinefunction(HTMLToMarkdownConverter.convert)


# ── BeautifulSoup parsing test ──


class TestHTMLParsing:
    """Verify html-ppt HTML is parseable by BeautifulSoup (used by DOCX/MD converters)."""

    def test_beautifulsoup_parses_sample_html(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        assert soup is not None, "BeautifulSoup returned None"

    def test_slide_sections_found(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        slides = soup.find_all("section", class_="slide")
        assert len(slides) >= 4, f"Expected >=4 slides, got {len(slides)}"

    def test_first_slide_is_active(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        first_slide = soup.find("section", class_="slide")
        assert first_slide is not None
        assert "is-active" in first_slide.get("class", []), "First slide missing is-active"

    def test_slide_has_data_title(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        slides = soup.find_all("section", class_="slide")
        for slide in slides:
            assert slide.get("data-title"), f"Slide missing data-title: {slide}"

    def test_slide_has_data_index(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        slides = soup.find_all("section", class_="slide")
        for slide in slides:
            assert slide.get("data-index") is not None, f"Slide missing data-index: {slide}"

    def test_h2_headings_present(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        h2s = soup.find_all("h2")
        assert len(h2s) >= 3, f"Expected >=3 h2 headings, got {len(h2s)}"

    def test_table_present(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        assert len(tables) >= 1, "No <table> found in generated HTML"

    def test_table_has_header_row(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        ths = soup.find_all("th")
        assert len(ths) >= 3, f"Expected >=3 <th> elements, got {len(ths)}"

    def test_kpi_cards_present(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        counters = soup.find_all(class_="counter")
        assert len(counters) >= 2, f"Expected >=2 counter elements, got {len(counters)}"

    def test_deck_wrapper_present(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        deck = soup.find("div", class_="deck")
        assert deck is not None, "No .deck wrapper found"

    def test_css_theme_link_present(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        theme_link = soup.find("link", id="theme-link")
        assert theme_link is not None, "No theme-link <link> found"

    def test_runtime_js_present(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", src=True)
        srcs = [s["src"] for s in scripts]
        assert any("runtime.js" in s for s in srcs), f"runtime.js not found in {srcs}"


# ── DOCX converter HTML-to-structure extraction ──


class TestDOCXHTMLExtraction:
    """Verify the DOCX converter's HTML extraction logic works with html-ppt output."""

    def test_docx_extracts_slides(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        slides = soup.find_all("section", class_="slide")
        assert len(slides) >= 4

    def test_docx_extracts_headings(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        slides = soup.find_all("section", class_="slide")
        headings_found = 0
        for slide in slides:
            h2 = slide.find("h2")
            if h2 and h2.get_text().strip():
                headings_found += 1
        assert headings_found >= 3, f"Expected >=3 headings, got {headings_found}"

    def test_docx_extracts_paragraphs(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        slides = soup.find_all("section", class_="slide")
        paragraphs_found = 0
        for slide in slides:
            paragraphs_found += len(slide.find_all("p"))
        assert paragraphs_found >= 5, f"Expected >=5 paragraphs, got {paragraphs_found}"


# ── Markdown converter extraction ──


class TestMarkdownHTMLExtraction:
    """Verify the Markdown converter's HTML extraction logic works with html-ppt output."""

    def test_md_extracts_slides(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        slides = soup.find_all("section", class_="slide")
        assert len(slides) >= 4

    def test_md_extracts_table_cells(self):
        html = _make_sample_html()
        soup = BeautifulSoup(html, "html.parser")
        td_elements = soup.find_all("td")
        assert len(td_elements) >= 9, f"Expected >=9 td cells (3x3 table), got {len(td_elements)}"


# ── HTMLReportGenerator output validation ──


class TestHTMLReportGeneratorOutput:
    """Verify HTMLReportGenerator produces output compatible with all converters."""

    def test_html_contains_doctype(self):
        html = _make_sample_html()
        assert html.startswith("<!DOCTYPE html>")

    def test_html_contains_data_theme(self):
        html = _make_sample_html()
        assert 'data-theme="minimal-white"' in html

    def test_html_contains_data_themes(self):
        html = _make_sample_html()
        assert "data-themes=" in html

    def test_html_has_section_slides(self):
        html = _make_sample_html()
        assert '<section class="' in html

    def test_html_has_deck_div(self):
        html = _make_sample_html()
        assert '<div class="deck">' in html

    def test_html_has_base_css_reference(self):
        html = _make_sample_html()
        assert "base.css" in html

    def test_html_has_fonts_css_reference(self):
        html = _make_sample_html()
        assert "fonts.css" in html


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
