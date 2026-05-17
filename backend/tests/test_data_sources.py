import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User

@pytest.mark.asyncio
async def test_crud_data_source(async_db):
    app.dependency_overrides[get_db] = lambda: async_db
    
    # Mock current active user
    mock_user = User(id=1, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create
        data = {
            "name": "Test Source",
            "type": "database",
            "config": {"host": "localhost", "port": 5432}
        }
        response = await ac.post("/api/v1/data-sources/", json=data)
        assert response.status_code == 200
        created = response.json()["data"]
        assert created["name"] == "Test Source"
        assert created["config"]["port"] == 5432
        source_id = created["id"]
        
        # Read All
        response = await ac.get("/api/v1/data-sources/")
        assert response.status_code == 200
        items = response.json()["data"]
        assert len(items) >= 1
        
        # Read One
        response = await ac.get(f"/api/v1/data-sources/{source_id}")
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Test Source"
        
        # Update
        update_data = {"status": "inactive"}
        response = await ac.put(f"/api/v1/data-sources/{source_id}", json=update_data)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "inactive"
        
        # Delete
        response = await ac.delete(f"/api/v1/data-sources/{source_id}")
        assert response.status_code == 200
        
        # Read One Not Found
        response = await ac.get(f"/api/v1/data-sources/{source_id}")
        assert response.status_code == 404
