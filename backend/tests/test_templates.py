import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.template import TemplateCreate, TemplateUpdate
from app.services.template import TemplateService

@pytest.mark.asyncio
async def test_template_service_crud_and_render(async_db):
    service = TemplateService()

    tmpl_in = TemplateCreate(
        name="SWOT_v1",
        scope="report",
        version="v1.0",
        content="# SWOT 分析\n\n优势: {{ strengths }}\n劣势: {{ weaknesses }}"
    )
    t = await service.create_template(async_db, tmpl_in)
    assert t.id > 0

    # Duplicate check
    with pytest.raises(ValueError):
        await service.create_template(async_db, tmpl_in)

    lst = await service.list_templates(async_db, scope="report")
    assert len(lst) >= 1

    # Test rendering
    rendered = await service.render_template(async_db, t.id, {"strengths": "技术好", "weaknesses": "无"})
    assert "技术好" in rendered
    assert "优势: 技术好" in rendered

    # Update
    up = TemplateUpdate(version="v1.1")
    t_up = await service.update_template(async_db, t.id, up)
    assert t_up.version == "v1.1"

    # Delete
    assert await service.delete_template(async_db, t.id) == True

@pytest.mark.asyncio
async def test_templates_api(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    user = User(username="tmplapi", email="api_tmpl@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    mock_user = User(id=user.id, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req = {"name": "PEST_v1", "scope": "report", "content": "P: {{ p }}"}
        res = await ac.post("/api/v1/templates", json=req)
        assert res.status_code == 200
        tid = res.json()["data"]["id"]

        res2 = await ac.post(f"/api/v1/templates/{tid}/render", json={"p": "政治稳定"})
        assert res2.status_code == 200
        assert "政治稳定" in res2.json()["data"]
