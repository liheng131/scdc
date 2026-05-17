import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.deps import get_current_active_user
from app.models.user import User
from app.agents.collector import CollectorAgent
from app.agents.collector import CollectorAgent
from app.agents.collector import CollectorAgent
from app.agents.collector import CollectorAgent
from app.agents.cleaner import CleanerAgent
from app.agents.analyzer import AnalyzerAgent
from app.agents.reporter import ReporterAgent
from app.agents.orchestrator import OrchestratorAgent
from app.schemas.agent import CollectorInput, CleanerInput, CollectedItem, AnalyzerInput, CleanedItem, ReporterInput, AnalyzerOutput, Insight, OrchestratorInput

@pytest.mark.asyncio
async def test_collector_agent_execution():
    agent = CollectorAgent()
    req = CollectorInput(task_id="task-123", topic="LLM Market 2026", max_items=2)
    res = await agent.execute(req)
    assert res.task_id == "task-123"
    assert res.success is True
    assert isinstance(res.items, list)

@pytest.mark.asyncio
async def test_cleaner_agent_execution():
    agent = CleanerAgent(min_content_length=15)
    raw1 = CollectedItem(source_type="search", source_uri="http://t1", title="T1", content="This is valid content long enough.")
    raw2 = CollectedItem(source_type="search", source_uri="http://t1", title="T1 Dup", content="This is valid content long enough.") # dup uri
    raw3 = CollectedItem(source_type="search", source_uri="http://t2", title="T2 Short", content="Too short") # too short
    raw4 = CollectedItem(source_type="crawler", source_uri="http://t3", title="T3", content="This is valid content long enough.") # dup content fingerprint

    req = CleanerInput(task_id="task-clean", raw_items=[raw1, raw2, raw3, raw4])
    res = await agent.execute(req)
    assert res.success is True
    assert len(res.cleaned_items) == 1
    assert res.total_removed == 3
    assert res.cleaned_items[0].source_uri == "http://t1"
    assert len(res.cleaned_items[0].content_chunks) >= 1

@pytest.mark.asyncio
async def test_analyzer_agent_degradation():
    agent = AnalyzerAgent()
    agent.ollama_url = "http://localhost:65432/invalid/endpoint" # Force connection failure

    item1 = CleanedItem(source_type="search", source_uri="http://source1", title="Source 1", summary="Summary 1")
    req = AnalyzerInput(task_id="task-analyze", topic="AI Test", cleaned_items=[item1])
    res = await agent.execute(req)
    assert res.success is True
    assert len(res.insights) == 1
    assert res.insights[0].evidence == ["http://source1"]

@pytest.mark.asyncio
async def test_reporter_agent_execution():
    agent = ReporterAgent()
    ins1 = Insight(conclusion="Market is growing fast", evidence=["http://ev1", "http://ev2"], confidence=0.9, category="trend")
    ins2 = Insight(conclusion="New competitor entering", evidence=["http://ev2"], confidence=0.85, category="competitor")

    ao = AnalyzerOutput(task_id="task-rep", success=True, summary="Executive summary test", insights=[ins1, ins2])
    req = ReporterInput(task_id="task-rep", topic="2026 AI Report", analyzer_output=ao)
    res = await agent.execute(req)

    assert res.success is True
    assert "# 深度市场洞察报告：2026 AI Report" in res.markdown_report
    assert "[^1]" in res.markdown_report
    assert "[^2]" in res.markdown_report
    assert "[^1]: [http://ev1](http://ev1)" in res.markdown_report
    assert len(res.sections) == 4
    assert len(res.chart_configs) == 1
    assert res.chart_configs[0]["series"][0]["type"] == "pie"

@pytest.mark.asyncio
async def test_orchestrator_agent_flow():
    recorded_states = []
    async def cb(tid, st, err):
        recorded_states.append((tid, st, err))

    orch = OrchestratorAgent(state_callback=cb)
    req = OrchestratorInput(task_id="task-orch-1", topic="FastAPI AI integration", max_items=1)
    res = await orch.execute(req)

    assert res.status == "completed"
    assert res.ended_at is not None
    assert res.reporter_output is not None
    assert len(recorded_states) == 6
    assert [s[1] for s in recorded_states] == ["queued", "collecting", "cleaning", "analyzing", "reporting", "completed"]

@pytest.mark.asyncio
async def test_agents_api():
    mock_user = User(id=1, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req = {"task_id": "task-abc", "topic": "AI Hardware", "max_items": 1}
        res = await ac.post("/api/v1/agents/collect", json=req)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["task_id"] == "task-abc"

        clean_req = {
            "task_id": "task-clean-api",
            "raw_items": [{
                "source_type": "search",
                "source_uri": "http://example.com/valid",
                "title": "Valid Title",
                "content": "This is a sufficiently long valid text content for testing cleaner api.",
                "metadata": {}
            }]
        }
        res_clean = await ac.post("/api/v1/agents/clean", json=clean_req)
        assert res_clean.status_code == 200
        clean_data = res_clean.json()["data"]
        assert clean_data["success"] is True
        assert len(clean_data["cleaned_items"]) == 1

        analyze_req = {
            "task_id": "task-analyze-api",
            "topic": "Market Test",
            "cleaned_items": [{
                "item_id": "uuid-1",
                "source_type": "search",
                "source_uri": "http://example.com/valid",
                "title": "Valid Title",
                "summary": "Summary text for testing.",
                "content_chunks": ["Chunk 1"],
                "relevance_score": 1.0,
                "metadata": {}
            }]
        }
        res_analyze = await ac.post("/api/v1/agents/analyze", json=analyze_req)
        assert res_analyze.status_code == 200
        analyze_data = res_analyze.json()["data"]
        assert analyze_data["success"] is True
        assert "insights" in analyze_data

        report_req = {
            "task_id": "task-report-api",
            "topic": "API Report Test",
            "analyzer_output": analyze_data,
            "include_charts": True
        }
        res_report = await ac.post("/api/v1/agents/report", json=report_req)
        assert res_report.status_code == 200
        report_data = res_report.json()["data"]
        assert report_data["success"] is True
        assert "markdown_report" in report_data
        assert len(report_data["sections"]) > 0

        orch_req = {
            "task_id": "task-orch-api",
            "topic": "Full flow API Test",
            "max_items": 1
        }
        res_orch = await ac.post("/api/v1/agents/orchestrate", json=orch_req)
        assert res_orch.status_code == 200
        orch_data = res_orch.json()["data"]
        assert orch_data["status"] == "completed"
        assert orch_data["reporter_output"]["success"] is True
