import pytest
import json
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.services.trigger import TriggerService

@pytest.mark.asyncio
async def test_trigger_service_sync(async_db):
    service = TriggerService()
    user = User(username="triggersync", email="trig@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    res = await service.run_qa_sync(async_db, topic="AI Hardware test", max_items=1, user_id=user.id)
    assert res["status"] == "completed"
    assert "completed" in res["recorded_runs"]
    assert res["reporter_output"] is not None

@pytest.mark.asyncio
async def test_trigger_qa_api(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    user = User(username="triggerapi", email="api_trig@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    mock_user = User(id=user.id, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Sync POST
        req = {"topic": "2026 AI Robotics", "max_items": 1}
        res = await ac.post("/api/v1/triggers/qa", json=req)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["status"] == "completed"
        assert data["task_id"] > 0

        # SSE GET Stream
        async with ac.stream("GET", "/api/v1/triggers/qa/stream?topic=Embodied+AI&max_items=1") as stream_res:
            assert stream_res.status_code == 200
            
            events = []
            async for line in stream_res.aiter_lines():
                if line.startswith("event:"):
                    events.append(line.strip())
            
            assert len(events) >= 3 # queued, collecting, ..., completed/done
            assert any("completed" in e or "done" in e for e in events)
