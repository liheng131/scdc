"""Tests for Chart.js integration in HTMLReportGenerator."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from app.services.html_report_generator import (
    HTMLReportGenerator,
    HTMLPageModel,
    LayoutType,
    HTMLTextBlock,
)


def test_chart_js_cdn_included():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="Test Report",
            layout=LayoutType.COVER,
            text_blocks=[HTMLTextBlock(text="Hello")],
        )
    ]
    html = gen.generate(pages)
    assert "chart.js@4.4.0" in html
    assert '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>' in html


def test_chart_bar_layout():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="Bar Chart",
            layout=LayoutType.CHART_BAR,
            chart_data={
                "labels": ["Q1", "Q2", "Q3", "Q4"],
                "datasets": [{"label": "Revenue", "data": [10, 20, 30, 40]}],
            },
        )
    ]
    html = gen.generate(pages)
    assert '<canvas id="chart_0"></canvas>' in html
    assert "new Chart" in html
    assert "type:'bar'" in html


def test_chart_line_layout():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="Line Chart",
            layout=LayoutType.CHART_LINE,
            chart_data={
                "labels": ["Jan", "Feb", "Mar"],
                "datasets": [{"label": "Growth", "data": [100, 150, 200]}],
            },
        )
    ]
    html = gen.generate(pages)
    assert '<canvas id="chart_0"></canvas>' in html
    assert "type:'line'" in html


def test_chart_pie_layout():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="Pie Chart",
            layout=LayoutType.CHART_PIE,
            chart_data={
                "labels": ["A", "B", "C"],
                "datasets": [{"data": [30, 50, 20]}],
            },
        )
    ]
    html = gen.generate(pages)
    assert '<canvas id="chart_0"></canvas>' in html
    assert "type:'pie'" in html


def test_chart_page_without_data_falls_back_to_content():
    gen = HTMLReportGenerator()
    pages = [
        HTMLPageModel(
            title="Empty Chart",
            layout=LayoutType.CHART_BAR,
            text_blocks=[HTMLTextBlock(text="No data")],
        )
    ]
    html = gen.generate(pages)
    assert '<canvas id="chart_0"></canvas>' not in html
    assert "No data" in html


def test_layout_enum_has_chart_types():
    assert LayoutType.CHART_BAR.value == "chart_bar"
    assert LayoutType.CHART_LINE.value == "chart_line"
    assert LayoutType.CHART_PIE.value == "chart_pie"


if __name__ == "__main__":
    test_chart_js_cdn_included()
    test_chart_bar_layout()
    test_chart_line_layout()
    test_chart_pie_layout()
    test_chart_page_without_data_falls_back_to_content()
    test_layout_enum_has_chart_types()
    print("All tests passed!")
