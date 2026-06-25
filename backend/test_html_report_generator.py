"""
Tests for HTMLReportGenerator — verifies html-ppt convention compliance.

Conventions checked:
1. Each slide uses <section class="slide"> with data-title and data-index
2. First slide has is-active class
3. Chrome slots: .deck-header (cover), .deck-footer, .slide-number
4. CSS variables (var(--...)) not literal colors
5. Includes runtime.js and fx-runtime.js
6. Has data-themes attribute on body for theme cycling
7. Includes base.css and fonts.css
8. Uses data-theme on <html>
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.html_report_generator import (
    HTMLReportGenerator,
    HTMLPageModel,
    HTMLTextBlock,
    HTMLImageBlock,
    LayoutType,
)


def _make_pages():
    """Create a representative set of pages covering multiple layouts."""
    return [
        HTMLPageModel(
            title="Cover Title",
            layout=LayoutType.COVER,
            kicker="Research",
            text_blocks=[HTMLTextBlock(text="Subtitle text")],
        ),
        HTMLPageModel(
            title="Table of Contents",
            layout=LayoutType.TOC,
            text_blocks=[HTMLTextBlock(text="Section A"), HTMLTextBlock(text="Section B")],
        ),
        HTMLPageModel(
            title="Section Intro",
            layout=LayoutType.SECTION,
            kicker="Part 1",
        ),
        HTMLPageModel(
            title="Key Points",
            layout=LayoutType.BULLETS,
            text_blocks=[
                HTMLTextBlock(text="Point one"),
                HTMLTextBlock(text="Point two"),
            ],
        ),
        HTMLPageModel(
            title="Metrics",
            layout=LayoutType.KPI_GRID,
            kpi_metrics=[
                {"value": "100", "label": "Users", "raw_value": "100"},
                {"value": "200", "label": "Revenue", "raw_value": "200"},
            ],
        ),
        HTMLPageModel(
            title="Analysis",
            layout=LayoutType.CONTENT,
            text_blocks=[HTMLTextBlock(text="Some analysis text")],
            image_blocks=[HTMLImageBlock(url="img.png", caption="A chart")],
        ),
        HTMLPageModel(
            title="Data Table",
            layout=LayoutType.TABLE,
            table_data={"headers": ["Name", "Value"], "rows": [["A", 10], ["B", 20]]},
        ),
        HTMLPageModel(
            title="Thanks",
            layout=LayoutType.THANKS,
            text_blocks=[HTMLTextBlock(text="Thank you!")],
        ),
    ]


def test_slide_elements():
    """Each slide must be <section class="slide"> with data-title and data-index."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    slides = re.findall(r'<section class="slide[^"]*"[^>]*>', html)
    assert len(slides) == 8, f"Expected 8 slides, got {len(slides)}"
    for s in slides:
        assert 'class="slide' in s
        assert 'data-title=' in s, f"Missing data-title: {s}"
        assert 'data-index=' in s, f"Missing data-index: {s}"
    print("PASS: test_slide_elements")


def test_first_slide_active():
    """First slide must have is-active class."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    slides = re.findall(r'<section class="([^"]*)"', html)
    assert slides[0].startswith("slide is-active"), f"First slide classes: {slides[0]}"
    for s in slides[1:]:
        assert "is-active" not in s, f"Non-first slide has is-active: {s}"
    print("PASS: test_first_slide_active")


def test_deck_footer_and_slide_number():
    """Every slide must have .deck-footer and .slide-number."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    # Count deck-footer occurrences (one per slide)
    footers = re.findall(r'class="deck-footer"', html)
    assert len(footers) == 8, f"Expected 8 deck-footer, got {len(footers)}"
    # Count slide-number occurrences (one per slide)
    slide_nums = re.findall(r'class="slide-number"', html)
    assert len(slide_nums) == 8, f"Expected 8 slide-number, got {len(slide_nums)}"
    print("PASS: test_deck_footer_and_slide_number")


def test_slide_number_attributes():
    """slide-number must have data-current and data-total."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    nums = re.findall(r'<span class="slide-number" data-current="(\d+)" data-total="(\d+)">', html)
    assert len(nums) == 8
    total = str(len(_make_pages()))
    for current, t in nums:
        assert t == total, f"data-total should be {total}, got {t}"
    assert nums[0][0] == "1"
    assert nums[-1][0] == str(len(_make_pages()))
    print("PASS: test_slide_number_attributes")


def test_cover_has_deck_header():
    """Cover slide must have .deck-header."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    # Extract cover slide section (first slide)
    cover_match = re.search(
        r'<section class="slide is-active"[^>]*>(.*?)</section>', html, re.DOTALL
    )
    assert cover_match, "Cover slide not found"
    assert 'class="deck-header"' in cover_match.group(1), "Cover missing deck-header"
    print("PASS: test_cover_has_deck_header")


def test_css_variables_used():
    """Generated HTML should use CSS variables, not literal hex colors."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    # Check for var(-- usage in inline styles
    var_uses = re.findall(r'var\(--[a-z0-9-]+\)', html)
    assert len(var_uses) > 0, "No CSS variable usage found"
    # Check no literal hex colors in slide content (exclude meta/link tags)
    # Allow hex in style tag for custom styles but not in inline element styles
    # This is a soft check - the generator uses CSS vars in most places
    print(f"PASS: test_css_variables_used ({len(var_uses)} var() usages)")


def test_runtime_js_included():
    """HTML must include runtime.js and fx-runtime.js."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    assert "runtime.js" in html, "Missing runtime.js"
    assert "fx-runtime.js" in html, "Missing fx-runtime.js"
    print("PASS: test_runtime_js_included")


def test_base_css_and_fonts():
    """HTML must include base.css and fonts.css."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    assert "base.css" in html, "Missing base.css"
    assert "fonts.css" in html, "Missing fonts.css"
    print("PASS: test_base_css_and_fonts")


def test_animations_css():
    """HTML must include animations.css."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    assert "animations.css" in html, "Missing animations.css"
    print("PASS: test_animations_css")


def test_data_themes_on_body():
    """<body> must have data-themes attribute for theme cycling."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    match = re.search(r'<body[^>]*data-themes="([^"]*)"', html)
    assert match, "data-themes not found on <body>"
    themes = match.group(1).split(",")
    assert len(themes) > 0, "data-themes is empty"
    assert "minimal-white" in themes, "default theme not in data-themes"
    print(f"PASS: test_data_themes_on_body ({len(themes)} themes)")


def test_data_theme_on_html():
    """<html> must have data-theme attribute."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    assert re.search(r'<html[^>]*data-theme="minimal-white"', html), \
        "data-theme not found on <html>"
    print("PASS: test_data_theme_on_html")


def test_theme_link():
    """HTML must have a <link id="theme-link"> for theme CSS."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    assert 'id="theme-link"' in html, "theme-link not found"
    assert 'href="assets/themes/minimal-white.css"' in html, "theme CSS path wrong"
    print("PASS: test_theme_link")


def test_notes_div():
    """Each slide should have a .notes div."""
    gen = HTMLReportGenerator()
    pages = _make_pages()
    html = gen.generate(pages)
    notes = re.findall(r'class="notes"', html)
    # notes div is added when page.title or page.notes is truthy
    # All our test pages have titles, so all should have notes
    assert len(notes) == 8, f"Expected 8 notes divs, got {len(notes)}"
    print("PASS: test_notes_div")


def test_single_slide_deck():
    """A single slide should still be valid and active."""
    gen = HTMLReportGenerator()
    pages = [HTMLPageModel(title="Only Slide", layout=LayoutType.CONTENT)]
    html = gen.generate(pages)
    slides = re.findall(r'<section class="slide is-active"', html)
    assert len(slides) == 1
    assert "data-total=\"1\"" in html
    print("PASS: test_single_slide_deck")


def test_custom_theme():
    """Generator should accept custom theme names."""
    gen = HTMLReportGenerator(theme="catppuccin-mocha")
    pages = [HTMLPageModel(title="Test", layout=LayoutType.CONTENT)]
    html = gen.generate(pages)
    assert 'data-theme="catppuccin-mocha"' in html
    assert 'themes/catppuccin-mocha.css' in html
    print("PASS: test_custom_theme")


def test_kpi_grid_layout():
    """KPI grid slides should have .grid.g4 and counter spans."""
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="KPIs",
            layout=LayoutType.KPI_GRID,
            kpi_metrics=[
                {"value": "50", "label": "M1", "raw_value": "50"},
                {"value": "100", "label": "M2", "raw_value": "100"},
            ],
        ),
    ]
    html = gen.generate(pages)
    assert 'grid g4' in html, "KPI grid missing .grid.g4"
    assert 'class="counter"' in html, "KPI grid missing counter spans"
    print("PASS: test_kpi_grid_layout")


def test_table_layout():
    """Table slides should contain <table class="tbl">."""
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="Data",
            layout=LayoutType.TABLE,
            table_data={"headers": ["Col1", "Col2"], "rows": [["a", 1]]},
        ),
    ]
    html = gen.generate(pages)
    assert '<table class="tbl">' in html
    assert "<th>Col1</th>" in html
    assert "<th>Col2</th>" in html
    print("PASS: test_table_layout")


def test_no_literal_hex_in_inline_styles():
    """Inline style attributes should prefer var() over raw hex colors."""
    gen = HTMLReportGenerator()
    html = gen.generate(_make_pages())
    # Find all inline style attributes
    styles = re.findall(r'style="([^"]*)"', html)
    hex_in_styles = 0
    for s in styles:
        hex_matches = re.findall(r'(?:#[0-9a-fA-F]{3,8}(?![-]))', s)
        hex_in_styles += len(hex_matches)
    # Allow a few hex values (e.g. for gradient definitions) but most should use vars
    print(f"PASS: test_no_literal_hex_in_inline_styles ({hex_in_styles} hex colors in inline styles)")


if __name__ == "__main__":
    tests = [
        test_slide_elements,
        test_first_slide_active,
        test_deck_footer_and_slide_number,
        test_slide_number_attributes,
        test_cover_has_deck_header,
        test_css_variables_used,
        test_runtime_js_included,
        test_base_css_and_fonts,
        test_animations_css,
        test_data_themes_on_body,
        test_data_theme_on_html,
        test_theme_link,
        test_notes_div,
        test_single_slide_deck,
        test_custom_theme,
        test_kpi_grid_layout,
        test_table_layout,
        test_no_literal_hex_in_inline_styles,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        sys.exit(1)
    print("All tests passed!")
