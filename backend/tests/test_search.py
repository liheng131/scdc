import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.deps import get_current_active_user
from app.models.user import User
from app.services.search import SearXNGService
from app.schemas.search import SearchRequest

@pytest.mark.asyncio
async def test_search_service_degradation():
    # Point to invalid port to test tenacity retry and graceful failure
    service = SearXNGService(base_url="http://localhost:59999")
    req = SearchRequest(query="AI Market", timeout=1)
    res = await service.search(req)
    assert res.success is False
    assert res.error is not None
    assert len(res.results) == 0

@pytest.mark.asyncio
async def test_search_api():
    mock_user = User(id=1, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req = {"query": "DeepSeek R1", "timeout": 1}
        res = await ac.post("/api/v1/search/query", json=req)
        assert res.status_code == 200
        data = res.json()["data"]
        # Since SearXNG isn't running on test env or we hit unreachable, it degrades gracefully
        assert isinstance(data["results"], list)
        assert "success" in data
