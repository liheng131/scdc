import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.notification import NotificationRuleCreate, NotificationRuleUpdate
from app.services.notification import NotificationService

@pytest.mark.asyncio
async def test_notification_service_crud(async_db):
    service = NotificationService()

    r1_in = NotificationRuleCreate(name="Admin Email", channel="email", trigger="report_ready", target="admin@example.com")
    r1 = await service.create_rule(async_db, r1_in)
    assert r1.id > 0
    assert r1.enabled == True

    r2_in = NotificationRuleCreate(name="DingTalk Group", channel="webhook", trigger="event_alert", target="http://invalid.webhook.local")
    r2 = await service.create_rule(async_db, r2_in)

    lst = await service.list_rules(async_db, enabled_only=True)
    assert len(lst) >= 2

    # Update
    up = NotificationRuleUpdate(enabled=False)
    r1_up = await service.update_rule(async_db, r1.id, up)
    assert r1_up.enabled == False

    # Notify test
    res = await service.notify(async_db, trigger="event_alert", title="Stock Crisis", content="Tesla dropped 10%")
    assert r2.id in res
    assert res[r2.id] == False # Invalid URL retry will fail gracefully

    # Delete
    del_ok = await service.delete_rule(async_db, r2.id)
    assert del_ok == True

@pytest.mark.asyncio
async def test_notifications_api(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    user = User(username="notifapi", email="api_notif@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    mock_user = User(id=user.id, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req = {"name": "WeCom Alert", "channel": "webhook", "trigger": "test_trig", "target": "http://test.local"}
        res = await ac.post("/api/v1/notifications/rules", json=req)
        assert res.status_code == 200
        rid = res.json()["data"]["id"]
        assert rid > 0

        res2 = await ac.get("/api/v1/notifications/rules")
        assert len(res2.json()["data"]) >= 1

        res3 = await ac.post("/api/v1/notifications/test", json={"trigger": "test_trig", "title": "T", "content": "C"})
        assert res3.status_code == 200
        assert str(rid) in res3.json()["data"]
