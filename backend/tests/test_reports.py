import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.task import Task
from app.schemas.report import ReportCreate, ReportUpdate
from app.services.report import ReportService

@pytest.mark.asyncio
async def test_report_service_crud_and_export(async_db):
    u = User(username="repsrv", email="srv_rep@example.com", password_hash="hash", role="admin")
    async_db.add(u)
    await async_db.commit()
    await async_db.refresh(u)

    t = Task(name="RepTask", type="research", trigger_mode="manual", status="created", created_by=u.id)
    async_db.add(t)
    await async_db.commit()
    await async_db.refresh(t)

    service = ReportService()
    rep_in = ReportCreate(
        task_id=t.id,
        title="特斯拉深度研报",
        version="v1.0",
        status="published",
        summary="马斯克宣布大降价",
        content_markdown="# 市场导向\n\n预计下季度交付增长20%"
    )
    r = await service.create_report(async_db, rep_in)
    assert r.id > 0

    lst = await service.list_reports(async_db, q="降价")
    assert len(lst) >= 1

    # Test export
    fn, mt, docx_bytes = await service.export_report(async_db, r.id, "docx")
    assert fn == f"report_{r.id}.docx"
    assert len(docx_bytes) > 100

    fn2, mt2, pdf_bytes = await service.export_report(async_db, r.id, "pdf")
    assert fn2 == f"report_{r.id}.pdf"
    assert len(pdf_bytes) > 100

    fn3, mt3, md_bytes = await service.export_report(async_db, r.id, "md")
    assert fn3 == f"report_{r.id}.md"
    assert b"20%" in md_bytes

@pytest.mark.asyncio
async def test_reports_api(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    user = User(username="repapi", email="api_rep@example.com", password_hash="hash", role="admin")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    t = Task(name="RepTask2", type="research", trigger_mode="manual", status="created", created_by=user.id)
    async_db.add(t)
    await async_db.commit()
    await async_db.refresh(t)

    mock_user = User(id=user.id, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req = {"task_id": t.id, "title": "API研报", "summary": "API摘要", "content_markdown": "# H1\nContent"}
        res = await ac.post("/api/v1/reports", json=req)
        assert res.status_code == 200
        rid = res.json()["data"]["id"]
        assert rid > 0

        res2 = await ac.get(f"/api/v1/reports/{rid}/export?fmt=pdf")
        assert res2.status_code == 200
        assert res2.headers["content-type"] == "application/pdf"
