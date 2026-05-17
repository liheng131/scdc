import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.services.task import TaskService
from app.schemas.task import TaskCreate, TaskUpdate, TaskRunCreate, TaskRunUpdate

@pytest.mark.asyncio
async def test_task_service_crud(async_db):
    service = TaskService()
    # Mock user creation
    user = User(username="taskcreator", email="tc@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    # 1. Create
    tc = TaskCreate(name="AI Trend 2026", type="deep", trigger_mode="manual", input_data={"topic": "AI"})
    task = await service.create_task(async_db, tc, user_id=user.id)
    assert task.id is not None
    assert task.status == "created"
    assert task.name == "AI Trend 2026"

    # 2. Get & List
    get_t = await service.get_task(async_db, task.id)
    assert get_t is not None
    assert get_t.name == "AI Trend 2026"

    tasks = await service.list_tasks(async_db, user_id=user.id)
    assert len(tasks) >= 1

    # 3. Update
    t_up = TaskUpdate(status="analyzing", output_ref="http://s3/output.md")
    updated_t = await service.update_task(async_db, task.id, t_up)
    assert updated_t.status == "analyzing"
    assert updated_t.output_ref == "http://s3/output.md"

    # 4. TaskRun Create & Update
    trc = TaskRunCreate(task_id=task.id, stage="collecting", status="pending")
    run = await service.create_task_run(async_db, trc)
    assert run.id is not None
    assert run.stage == "collecting"
    assert run.status == "pending"

    tru = TaskRunUpdate(status="completed", result={"collected_count": 5}, ended_at=datetime.utcnow())
    updated_run = await service.update_task_run(async_db, run.id, tru)
    assert updated_run.status == "completed"
    assert updated_run.result == {"collected_count": 5}

    # 5. Delete
    deleted = await service.delete_task(async_db, task.id)
    assert deleted is True
    assert await service.get_task(async_db, task.id) is None

@pytest.mark.asyncio
async def test_tasks_api(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    user = User(username="apicreator", email="api@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    mock_user = User(id=user.id, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create
        req = {"name": "API Task 1", "type": "quick", "trigger_mode": "manual", "input_data": {"query": "test"}}
        res = await ac.post("/api/v1/tasks", json=req)
        assert res.status_code == 200
        data = res.json()["data"]
        task_id = data["id"]
        assert data["name"] == "API Task 1"
        assert data["status"] == "created"

        # Get
        res_get = await ac.get(f"/api/v1/tasks/{task_id}")
        assert res_get.status_code == 200
        assert res_get.json()["data"]["name"] == "API Task 1"

        # List
        res_list = await ac.get("/api/v1/tasks")
        assert res_list.status_code == 200
        assert len(res_list.json()["data"]) >= 1

        # Create Run
        run_req = {"task_id": task_id, "stage": "cleaning", "status": "running"}
        res_run = await ac.post(f"/api/v1/tasks/{task_id}/runs", json=run_req)
        assert res_run.status_code == 200
        assert res_run.json()["data"]["stage"] == "cleaning"

        # Update
        up_req = {"status": "completed"}
        res_up = await ac.put(f"/api/v1/tasks/{task_id}", json=up_req)
        assert res_up.status_code == 200
        assert res_up.json()["data"]["status"] == "completed"

        # Delete
        res_del = await ac.delete(f"/api/v1/tasks/{task_id}")
        assert res_del.status_code == 200
        assert res_del.json()["data"] is True
