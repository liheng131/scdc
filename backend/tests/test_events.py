import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.event_rule import EventRuleCreate
from app.services.event_trigger import EventTriggerService

@pytest.mark.asyncio
async def test_event_trigger_service_crud(async_db):
    service = EventTriggerService()
    user = User(username="eventuser", email="ev@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    # Keyword rule
    rc1 = EventRuleCreate(name="Crisis Alert", event_type="keyword", keywords=["bankruptcy", "crisis"], target_topic="Company Risk")
    r1 = await service.create_rule(async_db, rc1, user.id)
    assert r1.id > 0

    # Metric rule
    rc2 = EventRuleCreate(name="Stock Drop", event_type="metric", threshold=5.0, target_topic="Stock Evaluation")
    r2 = await service.create_rule(async_db, rc2, user.id)

    lst = await service.list_rules(async_db, user.id)
    assert len(lst) >= 2

    # Process Webhook matching
    w1 = {"text": "Huge financial crisis reported today"}
    res1 = await service.process_webhook(async_db, w1)
    assert r1.id in res1["matched_rules"]
    assert len(res1["triggered_tasks"]) == 1

    # Throttle test (5 mins cooldown)
    res2 = await service.process_webhook(async_db, w1)
    assert len(res2["matched_rules"]) == 0 # Throttled!

    # Process Webhook metric matching
    w2 = {"metric_value": -6.5}
    res3 = await service.process_webhook(async_db, w2)
    assert r2.id in res3["matched_rules"]
    assert len(res3["triggered_tasks"]) == 1

@pytest.mark.asyncio
async def test_events_api(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    user = User(username="evapi", email="api_ev@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    mock_user = User(id=user.id, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create rule
        req = {"name": "Tech Breakthrough", "event_type": "keyword", "keywords": ["breakthrough"], "target_topic": "AI Hardware"}
        res = await ac.post("/api/v1/events/rules", json=req)
        assert res.status_code == 200
        rid = res.json()["data"]["id"]
        assert rid > 0

        # List
        res2 = await ac.get("/api/v1/events/rules")
        assert len(res2.json()["data"]) >= 1

        # Webhook
        w_req = {"text": "A massive AI breakthrough was revealed"}
        w_res = await ac.post("/api/v1/events/webhook", json=w_req)
        assert w_res.status_code == 200
        assert rid in w_res.json()["data"]["matched_rules"]
