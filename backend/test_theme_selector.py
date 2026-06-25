"""Tests for ThemeSelector service."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.services.theme_selector import ThemeSelector


def test_financial_topic():
    sel = ThemeSelector()
    theme = sel.select_theme("2024年Q3财务分析报告")
    assert theme == "corporate-clean", f"Expected corporate-clean, got {theme}"


def test_tech_topic():
    sel = ThemeSelector()
    theme = sel.select_theme("Kubernetes微服务架构技术分享")
    assert theme == "tokyo-night", f"Expected tokyo-night, got {theme}"


def test_consumer_topic():
    sel = ThemeSelector()
    theme = sel.select_theme("小红书种草好物推荐")
    assert theme == "xiaohongshu-white", f"Expected xiaohongshu-white, got {theme}"


def test_academic_topic():
    sel = ThemeSelector()
    theme = sel.select_theme("学术论文研究方法论分享")
    assert theme == "academic-paper", f"Expected academic-paper, got {theme}"


def test_default_fallback():
    sel = ThemeSelector()
    theme = sel.select_theme("random unrelated topic xyz")
    assert theme == "minimal-white", f"Expected minimal-white, got {theme}"


def test_empty_input():
    sel = ThemeSelector()
    theme = sel.select_theme("")
    assert theme == "minimal-white", f"Expected minimal-white, got {theme}"


if __name__ == "__main__":
    test_financial_topic()
    test_tech_topic()
    test_consumer_topic()
    test_academic_topic()
    test_default_fallback()
    test_empty_input()
    print("All tests passed!")
