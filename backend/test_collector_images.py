"""Tests for CollectorOutput.extracted_images field."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend")) if os.path.isdir(os.path.join(os.path.dirname(__file__), "backend")) else sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.schemas.agent import CollectorOutput


def test_collector_output_has_extracted_images_field():
    output = CollectorOutput(task_id="t1", success=True)
    assert hasattr(output, "extracted_images")


def test_extracted_images_defaults_to_empty_list():
    output = CollectorOutput(task_id="t1", success=True)
    assert output.extracted_images == []


def test_extracted_images_accepts_list_of_dicts():
    images = [
        {"url": "https://example.com", "title": "Ex", "base64": "abc", "type": "web_screenshot"},
        {"url": "https://foo.bar", "title": "Fb", "base64": "def", "type": "web_screenshot"},
    ]
    output = CollectorOutput(task_id="t1", success=True, extracted_images=images)
    assert len(output.extracted_images) == 2
    assert output.extracted_images[0]["url"] == "https://example.com"
    assert output.extracted_images[1]["type"] == "web_screenshot"
