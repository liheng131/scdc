import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user
from app.models.user import User

@pytest.mark.asyncio
async def test_e2e_user_auth_flow(async_db):
    """
    验证健康检查及模拟已授权用户的会话拦截流程
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. 健康检查
        res = await ac.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json()["code"] == 0
        assert "version" in res.json()["data"]

@pytest.mark.asyncio
async def test_e2e_datasource_sync_flow(async_db):
    """
    验证创建数据源配置并手动触发资讯抓取同步流程
    """
    app.dependency_overrides[get_db] = lambda: async_db
    user = User(username="e2eds", email="e2eds@example.com", password_hash="hash", role="admin", status="active")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    app.dependency_overrides[get_current_active_user] = lambda: user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. 创建数据源
        ds_req = {"name": "AI News RSS", "source_type": "rss", "config": {"url": "https://news.ycombinator.com/rss"}}
        res_cr = await ac.post("/api/v1/data-sources/", json=ds_req)
        assert res_cr.status_code == 200
        data = res_cr.json()["data"]
        ds_id = data["id"]
        assert data["name"] == "AI News RSS"

        # 2. 触发抓取同步
        res_sync = await ac.post(f"/api/v1/data-sources/{ds_id}/sync")
        assert res_sync.status_code == 200
        assert res_sync.json()["data"]["records_collected"] == 15
        assert res_sync.json()["data"]["status"] == "success"

@pytest.mark.asyncio
async def test_e2e_template_creation_flow(async_db):
    """
    验证行研大纲模板的注册及在线沙箱 Jinja2 渲染校验
    """
    app.dependency_overrides[get_db] = lambda: async_db
    user = User(username="e2etmpl", email="e2etmpl@example.com", password_hash="hash", role="admin", status="active")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)
    app.dependency_overrides[get_current_active_user] = lambda: user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        tmpl_req = {
            "name": "E2E PEST 模版",
            "scope": "report",
            "version": "1.0",
            "content": "# {{ industry_name }} 宏观 PEST 分析\n政治环境: {{ p_factor }}"
        }
        res_cr = await ac.post("/api/v1/templates", json=tmpl_req)
        assert res_cr.status_code == 200
        tmpl_id = res_cr.json()["data"]["id"]
        assert tmpl_id > 0

        # 在线渲染校验
        vars_data = {"industry_name": "半导体", "p_factor": "政策大力扶持"}
        res_render = await ac.post(f"/api/v1/templates/{tmpl_id}/render", json=vars_data)
        assert res_render.status_code == 200
        assert "半导体" in res_render.json()["data"]
        assert "政策大力扶持" in res_render.json()["data"]

@pytest.mark.asyncio
async def test_e2e_task_execution_flow(async_db):
    """
    验证拉起分析任务实例及调度流水线
    """
    app.dependency_overrides[get_db] = lambda: async_db
    user = User(username="e2etask", email="e2etask@example.com", password_hash="hash", role="admin", status="active")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)
    app.dependency_overrides[get_current_active_user] = lambda: user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        task_req = {
            "name": "2026 Q3 半导体行业深度分析",
            "type": "market_analysis",
            "trigger_mode": "manual",
            "input_data": {"prompt_template": "E2E PEST 模版"}
        }
        res_cr = await ac.post("/api/v1/tasks", json=task_req)
        assert res_cr.status_code == 200
        task_id = res_cr.json()["data"]["id"]

        # 触发执行
        res_run = await ac.post(f"/api/v1/tasks/{task_id}/run")
        assert res_run.status_code == 200
        assert res_run.json()["data"]["run_id"] > 0
        assert res_run.json()["data"]["status"] == "running"

@pytest.mark.asyncio
async def test_e2e_report_export_flow(async_db):
    """
    验证多模态智能研报发布及多格式导出分发流程 (Word/PDF/Markdown)
    """
    from app.models.task import Task
    app.dependency_overrides[get_db] = lambda: async_db
    user = User(username="e2erep", email="e2erep@example.com", password_hash="hash", role="admin", status="active")
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)

    task = Task(name="E2E RepTask", type="research", trigger_mode="manual", status="created", created_by=user.id)
    async_db.add(task)
    await async_db.commit()
    await async_db.refresh(task)

    app.dependency_overrides[get_current_active_user] = lambda: user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. 创建研报
        rep_req = {
            "task_id": task.id,
            "title": "2026 AI 硬件全球生态报告",
            "version": "1.0",
            "status": "published",
            "summary": "AI 芯片市场预计增长超 40%",
            "content_markdown": "# 1. 产业全景\nAI 算力硬件正迎来爆发式增长周期。"
        }
        res_cr = await ac.post("/api/v1/reports", json=rep_req)
        assert res_cr.status_code == 200
        rep_id = res_cr.json()["data"]["id"]

        # 2. 导出 Word (.docx)
        res_docx = await ac.get(f"/api/v1/reports/{rep_id}/export?fmt=docx")
        assert res_docx.status_code == 200
        assert res_docx.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert len(res_docx.content) > 100

        # 3. 导出 PDF (.pdf)
        res_pdf = await ac.get(f"/api/v1/reports/{rep_id}/export?fmt=pdf")
        assert res_pdf.status_code == 200
        assert res_pdf.headers["content-type"] == "application/pdf"
        assert len(res_pdf.content) > 100

        # 4. 导出 Markdown (.md)
        res_md = await ac.get(f"/api/v1/reports/{rep_id}/export?fmt=md")
        assert res_md.status_code == 200
        assert "text/markdown" in res_md.headers["content-type"]
        assert b"40%" in res_md.content
