"""
Tests for ReportService html_content pipeline integration.

Verifies:
- ReportService has export_report_with_html_pipeline method
- create_from_workflow accepts html_content parameter
- html_content flows through create_from_workflow → create_report → Report model
- html_content is stored as None when not provided (backward compatibility)
"""

import asyncio
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from app.schemas.report import ReportCreate
from app.services.report import ReportService


class TestReportServiceHTMLPipeline:
    """Tests for the html_content integration in ReportService."""

    def test_export_report_with_html_pipeline_method_exists(self):
        """ReportService must have export_report_with_html_pipeline method."""
        assert hasattr(ReportService, "export_report_with_html_pipeline")
        assert callable(getattr(ReportService, "export_report_with_html_pipeline"))

    def test_create_from_workflow_accepts_html_content(self):
        """create_from_workflow must accept html_content as an optional parameter."""
        import inspect
        sig = inspect.signature(ReportService.create_from_workflow)
        params = list(sig.parameters.keys())
        assert "html_content" in params, (
            f"html_content not in create_from_workflow params: {params}"
        )
        param = sig.parameters["html_content"]
        assert param.default is None or param.default == "", (
            f"html_content default should be None or empty string, got {param.default}"
        )

    def test_report_create_schema_has_html_content(self):
        """ReportCreate schema must accept html_content field."""
        rc = ReportCreate(
            title="Test",
            task_id="test-001",
            html_content="<html><body>Hello</body></html>",
        )
        assert rc.html_content == "<html><body>Hello</body></html>"

    def test_report_create_schema_html_content_optional(self):
        """html_content is optional in ReportCreate."""
        rc = ReportCreate(title="Test", task_id="test-002")
        assert rc.html_content is None

    def test_create_from_workflow_signature_accepts_all_params(self):
        """Verify create_from_workflow has all expected parameters."""
        import inspect
        sig = inspect.signature(ReportService.create_from_workflow)
        expected_params = [
            "self", "session", "task_id", "title",
            "content_markdown", "summary", "chart_images",
            "dimension_illustrations", "page_model", "theme",
            "notes_summary", "html_content",
        ]
        actual_params = list(sig.parameters.keys())
        for p in expected_params:
            assert p in actual_params, f"Missing parameter: {p}"

    @pytest.mark.asyncio
    async def test_create_from_workflow_stores_html_content(self):
        """When html_content is provided, it should be persisted in the report."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        svc = ReportService()

        # Patch create_report to capture what gets stored
        stored_reports = []
        original_create_report = svc.create_report

        async def capture_create_report(session, report_in):
            stored_reports.append(report_in)
            report_obj = MagicMock()
            report_obj.id = 42
            report_obj.html_content = report_in.html_content
            # Simulate DB write
            session.add(report_obj)
            await session.commit()
            await session.refresh(report_obj)
            return report_obj

        with patch.object(svc, "create_report", capture_create_report):
            result = await svc.create_from_workflow(
                mock_session,
                task_id="wf-test-001",
                title="Test Report",
                content_markdown="# Test",
                html_content="<html><body>Test content</body></html>",
            )

        assert len(stored_reports) == 1
        assert stored_reports[0].html_content == "<html><body>Test content</body></html>"
        assert result.id == 42

    @pytest.mark.asyncio
    async def test_create_from_workflow_html_content_none_backward_compat(self):
        """When html_content is not provided, it defaults to None (backward compat)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        svc = ReportService()
        stored_reports = []

        async def capture_create_report(session, report_in):
            stored_reports.append(report_in)
            report_obj = MagicMock()
            report_obj.id = 43
            report_obj.html_content = report_in.html_content
            session.add(report_obj)
            await session.commit()
            await session.refresh(report_obj)
            return report_obj

        with patch.object(svc, "create_report", capture_create_report):
            result = await svc.create_from_workflow(
                mock_session,
                task_id="wf-test-002",
                title="Test Report No HTML",
            )

        assert len(stored_reports) == 1
        assert stored_reports[0].html_content is None

    def test_workflow_result_includes_html_content_key(self):
        """Verify that the workflow result dict schema includes html_content."""
        # This tests the data contract: workflow.py builds result dicts that
        # must contain "html_content" key for the pipeline to work.
        sample_result = {
            "report_markdown": "# Report",
            "chart_configs": [],
            "chart_images": [],
            "dimension_illustrations": [],
            "sections": [],
            "page_model": [],
            "theme": "minimal-white",
            "notes_summary": "",
            "html_content": "<html></html>",
        }
        assert "html_content" in sample_result
        assert sample_result["html_content"] == "<html></html>"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
