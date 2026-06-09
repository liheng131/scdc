import pytest
from app.agents.collector import CollectorAgent
from app.agents.cleaner import CleanerAgent
from app.agents.analyzer import AnalyzerAgent
from app.agents.reporter import ReporterAgent
from app.schemas.agent import CollectorInput, CleanerInput, AnalyzerInput, ReporterInput


@pytest.mark.asyncio
async def test_full_pipeline():
    # AnySearch 始终可用，无需 skip 条件
    task_id = "e2e-test-001"
    topic = "2025年AI芯片市场趋势"

    collector = CollectorAgent()
    col_out = await collector.execute(CollectorInput(task_id=task_id, topic=topic, max_items=3))
    assert col_out.success, f"Collector failed: {col_out.error}"
    assert len(col_out.items) > 0, "No items collected"
    print(f"[PASS] Collector: {len(col_out.items)} items")

    cleaner = CleanerAgent()
    cln_out = await cleaner.execute(CleanerInput(task_id=task_id, raw_items=col_out.items))
    assert cln_out.success, f"Cleaner failed: {cln_out.error}"
    assert len(cln_out.cleaned_items) > 0, "No cleaned items"
    print(f"[PASS] Cleaner: {len(cln_out.cleaned_items)} items (removed {cln_out.total_removed})")

    analyzer = AnalyzerAgent()
    ana_out = await analyzer.execute(AnalyzerInput(
        task_id=task_id, topic=topic,
        cleaned_items=cln_out.cleaned_items,
        dimensions=["宏观经济环境", "行业形势与趋势", "细分板块分析", "竞争格局与对手"]
    ))
    assert ana_out.success, f"Analyzer failed: {ana_out.error}"
    assert len(ana_out.summary) > 50, f"Summary too short: {len(ana_out.summary)} chars"
    assert len(ana_out.insights) > 0, "No insights generated"
    print(f"[PASS] Analyzer: {len(ana_out.insights)} insights, {len(ana_out.summary)} char summary")

    reporter = ReporterAgent()
    rep_out = await reporter.execute(ReporterInput(
        task_id=task_id, topic=topic,
        analyzer_output=ana_out,
        include_charts=True,
        dimensions=["宏观经济环境", "行业形势与趋势", "细分板块分析", "竞争格局与对手"]
    ))
    assert rep_out.success, f"Reporter failed: {rep_out.error}"
    assert len(rep_out.markdown_report) > 200, f"Report too short: {len(rep_out.markdown_report)} chars"
    print(f"[PASS] Reporter: {len(rep_out.markdown_report)} char report, {len(rep_out.chart_configs)} charts")

    print("\n=== ALL TESTS PASSED ===")