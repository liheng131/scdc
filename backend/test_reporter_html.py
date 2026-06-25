"""Tests for ReporterAgent HTML generation."""

import asyncio
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from app.agents.reporter import ReporterAgent
from app.schemas.agent import (
    ReporterInput,
    AnalyzerOutput,
    Insight,
    StructuredMetric,
    MetricDataPoint,
)


def _make_reporter_input(
    topic: str = "AI芯片市场分析",
    summary: str = "全球AI芯片市场正在快速增长",
    dimensions: list = None,
    insights: list = None,
    structured_metrics: list = None,
) -> ReporterInput:
    if dimensions is None:
        dimensions = ["宏观经济环境", "行业形势与趋势"]
    if insights is None:
        insights = [
            Insight(
                conclusion="全球AI芯片市场规模持续扩大",
                analysis="2024年市场规模达到800亿美元",
                confidence=0.85,
                dimension="宏观经济环境",
            ),
            Insight(
                conclusion="国产AI芯片替代加速",
                analysis="国产化率提升至35%",
                confidence=0.75,
                dimension="行业形势与趋势",
            ),
        ]
    if structured_metrics is None:
        structured_metrics = [
            StructuredMetric(
                metric_name="AI芯片市场规模",
                metric_type="yearly_trend",
                unit="亿美元",
                dimension="宏观经济环境",
                data_points=[
                    MetricDataPoint(label="2022", value=500),
                    MetricDataPoint(label="2023", value=650),
                    MetricDataPoint(label="2024", value=800),
                ],
            ),
        ]

    analyzer_output = AnalyzerOutput(
        task_id="test-task-001",
        success=True,
        summary=summary,
        insights=insights,
        structured_metrics=structured_metrics,
    )
    return ReporterInput(
        task_id="test-task-001",
        topic=topic,
        analyzer_output=analyzer_output,
        dimensions=dimensions,
    )


def test_html_content_field_exists():
    """ReporterOutput should have an html_content field."""
    from app.schemas.agent import ReporterOutput
    out = ReporterOutput(
        task_id="t", success=True, markdown_report="md", html_content="<html></html>"
    )
    assert out.html_content == "<html></html>"


def test_html_content_default_empty():
    """html_content defaults to empty string."""
    from app.schemas.agent import ReporterOutput
    out = ReporterOutput(task_id="t", success=True, markdown_report="md")
    assert out.html_content == ""


def test_build_html_report_produces_valid_html():
    """_build_html_report produces HTML with slide elements."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input()

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
        structured_metrics=input_data.analyzer_output.structured_metrics,
    )

    assert isinstance(html, str)
    assert len(html) > 500
    assert "<!DOCTYPE html>" in html
    assert '<html lang="zh-CN"' in html
    assert "<section" in html
    assert 'class="slide' in html


def test_html_includes_runtime_and_css():
    """HTML output must reference runtime.js and base.css."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input()

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
    )

    assert "runtime.js" in html
    assert "base.css" in html
    assert "animations.css" in html


def test_html_has_correct_theme():
    """HTML output should have the specified theme."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input()

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
        theme="tokyo-night",
    )

    assert 'data-theme="tokyo-night"' in html
    assert "tokyo-night.css" in html


def test_html_has_cover_and_toc():
    """HTML should contain cover and TOC slides."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input()

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
    )

    assert input_data.topic in html
    assert "Contents" in html
    assert "Executive Summary" in html


def test_html_has_dimension_sections():
    """HTML should contain dimension section pages."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input()

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
    )

    assert "宏观经济环境" in html
    assert "行业形势与趋势" in html
    assert "Thank You" in html


def test_html_includes_kpi_metrics():
    """HTML should include KPI metrics when structured_metrics provided."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input()

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
        structured_metrics=input_data.analyzer_output.structured_metrics,
    )

    assert "AI芯片市场规模" in html
    assert "800" in html


def test_theme_selector_auto_selects():
    """When no theme provided, ThemeSelector is used."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input(topic="金融市场分析报告")

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
    )

    # corporate-clean matches financial keywords
    assert "corporate-clean" in html


def test_html_slide_count():
    """HTML should have at least 4 slides (cover + toc + content + thanks)."""
    reporter = ReporterAgent()
    input_data = _make_reporter_input()

    html = reporter._build_html_report(
        topic=input_data.topic,
        summary=input_data.analyzer_output.summary,
        insights=input_data.analyzer_output.insights,
        dimensions=input_data.dimensions,
    )

    slide_count = html.count('<section class="slide')
    assert slide_count >= 4, f"Expected >= 4 slides, got {slide_count}"


if __name__ == "__main__":
    tests = [
        test_html_content_field_exists,
        test_html_content_default_empty,
        test_build_html_report_produces_valid_html,
        test_html_includes_runtime_and_css,
        test_html_has_correct_theme,
        test_html_has_cover_and_toc,
        test_html_has_dimension_sections,
        test_html_includes_kpi_metrics,
        test_theme_selector_auto_selects,
        test_html_slide_count,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS  {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {test_fn.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(1 if failed else 0)
