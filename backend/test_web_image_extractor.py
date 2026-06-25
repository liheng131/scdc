"""Tests for WebImageExtractor service."""
import sys
import os
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))
sys.path.insert(0, os.path.dirname(__file__))

from app.services.web_image_extractor import WebImageExtractor, web_image_extractor


def test_extractor_initialization():
    extractor = WebImageExtractor()
    assert extractor is not None
    assert extractor.renderer is not None


def test_singleton_initialization():
    assert web_image_extractor is not None
    assert isinstance(web_image_extractor, WebImageExtractor)


def test_extract_method_exists():
    assert hasattr(WebImageExtractor, "extract_chart_screenshots")
    method = getattr(WebImageExtractor, "extract_chart_screenshots")
    assert callable(method)


def test_extract_method_signature():
    sig = inspect.signature(WebImageExtractor.extract_chart_screenshots)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "urls" in params
    assert "max_images" in params
    assert "timeout" in params


def test_extract_default_params():
    sig = inspect.signature(WebImageExtractor.extract_chart_screenshots)
    assert sig.parameters["max_images"].default == 10
    assert sig.parameters["timeout"].default == 30000


if __name__ == "__main__":
    test_extractor_initialization()
    test_singleton_initialization()
    test_extract_method_exists()
    test_extract_method_signature()
    test_extract_default_params()
    print("All tests passed!")
