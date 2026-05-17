import pytest
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.schedule import ScheduleCreate
from app.services.scheduler import SchedulerService, match_cron

def test_match_cron():
    dt1 = datetime(2026, 5, 17, 8, 0, 0) # 2026-05-17 is Sunday (weekday 6)
    assert match_cron("0 8 * * *", dt1) == True
    assert match_cron("30 8 * * *", dt1) == False
    assert match_cron("0 8 * * 6", dt1) == True # 6 is Sunday in Python weekday()
    assert match_cron("*/15 8 * * *", datetime(2026, 5, 17, 8, 15, 0)) == True

@pytest.mark.asyncio
async def test_scheduler_service_crud(async_db):
    service = SchedulerService()
    user = User(username="scheduleruser", email="sched@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    sc = ScheduleCreate(name="Daily Report", topic="Autonomous Driving", cron_expr="0 8 * * *", max_items=1)
    out = await service.create_schedule(async_db, sc, user.id)
    assert out.task_id > 0
    assert out.status == "scheduled"

    lst = await service.list_schedules(async_db, user.id)
    assert len(lst) == 1
    assert lst[0].cron_expr == "0 8 * * *"

    triggered = await service.trigger_job(async_db, out.task_id)
    assert triggered == True

    deleted = await service.delete_schedule(async_db, out.task_id)
    assert deleted == True
    lst2 = await service.list_schedules(async_db, user.id)
    assert len(lst2) == 0

@pytest.mark.asyncio
async def test_schedules_api(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    user = User(username="schedapi", email="api_sched@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    mock_user = User(id=user.id, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create
        req = {"name": "Tech Weekly", "topic": "AI Hardware", "cron_expr": "0 9 * * 1", "max_items": 1}
        res = await ac.post("/api/v1/schedules", json=req)
        assert res.status_code == 200
        tid = res.json()["data"]["task_id"]
        assert tid > 0

        # List
        res2 = await ac.get("/api/v1/schedules")
        assert len(res2.json()["data"]) >= 1

        # Trigger
        res3 = await ac.post(f"/api/v1/schedules/{tid}/trigger")
        assert res3.status_code == 200

        # Delete
        res4 = await ac.delete(f"/api/v1/schedules/{tid}")
        assert res4.status_code == 200
