"""
Tests for ReporterAgent image embedding in HTML report.

Verifies that:
- user_images and web_images are rendered as IMAGE_GRID pages with base64 data URLs
- HTML generation without images does not include IMAGE_GRID
"""

import pytest
from typing import List, Dict, Any

from app.agents.reporter import ReporterAgent
from app.schemas.agent import Insight


def _make_insights(dims: List[str]) -> List[Insight]:
    return [
        Insight(conclusion=f"Insight for {d}", analysis=f"Analysis for {d}", confidence=0.85, dimension=d)
        for d in dims
    ]


class TestBuildHtmlReportImages:

    def _call_build(self, **kwargs) -> str:
        agent = ReporterAgent()
        defaults = dict(
            topic="AI Chip Market",
            summary="Market overview",
            insights=_make_insights(["Market Size", "Competition"]),
            dimensions=["Market Size", "Competition"],
            theme="minimal-white",
        )
        defaults.update(kwargs)
        return agent._build_html_report(**defaults)

    def test_no_images_no_image_grid(self):
        html = self._call_build()
        assert "参考图片" not in html
        assert 'class="image-card anim-rise-in"' not in html

    def test_user_images_embedded_as_base64(self):
        user_images = [
            {"base64": "AAAA", "caption": "User Chart 1"},
            {"base64": "BBBB", "caption": "User Chart 2"},
        ]
        html = self._call_build(user_images=user_images)
        assert "data:image/png;base64,AAAA" in html
        assert "data:image/png;base64,BBBB" in html
        assert "User Chart 1" in html
        assert "User Chart 2" in html

    def test_web_images_embedded_as_base64(self):
        web_images = [
            {"base64": "CCCC", "source_url": "https://example.com", "caption": "Web Screenshot"},
        ]
        html = self._call_build(web_images=web_images)
        assert "data:image/png;base64,CCCC" in html
        assert "Web Screenshot" in html

    def test_both_image_types_combined(self):
        user_images = [{"base64": "UUUU", "caption": "User Pic"}]
        web_images = [{"base64": "WWWW", "source_url": "https://x.com", "caption": "Web Pic"}]
        html = self._call_build(user_images=user_images, web_images=web_images)
        assert "data:image/png;base64,UUUU" in html
        assert "data:image/png;base64,WWWW" in html

    def test_image_grid_layout_used(self):
        user_images = [{"base64": "TEST1"}]
        html = self._call_build(user_images=user_images)
        assert "参考图片" in html
        assert 'class="image-card anim-rise-in"' in html

    def test_empty_image_lists_no_grid(self):
        html = self._call_build(user_images=[], web_images=[])
        assert "参考图片" not in html

    def test_images_without_base64_skipped(self):
        user_images = [{"caption": "No base64"}]
        html = self._call_build(user_images=user_images)
        assert "参考图片" not in html

    def test_web_images_without_caption_use_title(self):
        web_images = [{"base64": "DATA", "title": "Auto Title", "source_url": "https://y.com"}]
        html = self._call_build(web_images=web_images)
        assert "Auto Title" in html
        assert "data:image/png;base64,DATA" in html
