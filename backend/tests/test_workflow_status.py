"""
Spec 2 集成测试 - /api/v1/workflow/{id}/status 端点

通过 FastAPI TestClient 直接调端点,验证:
- 200: 返回 stage_output + stage_state + sse_url 建议
- 404: 不存在的 workflow
- 401: 未认证
- sse_url 在 running 状态时正确,在 awaiting_confirmation 时为 null(因为是确认端点不是启动端点)
- 各阶段的 stage_output 透传
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user, get_current_active_user_sse
from app.models.user import User
from app.services.workflow import (
    workflow_service,
    StageState,
    WorkflowState,
)


def _create_test_user() -> User:
    return User(
        id=999,
        username="test_status_user",
        email="test_status@example.com",
        password_hash="hash",
        role="admin",
        status="active",
    )


def _build_workflow_in_state(stage: str, stage_state: str,
                              stage_output: dict = None,
                              history_len: int = 0) -> str:
    """手动把 workflow_service 内部缓存填入一个测试 workflow,返回 workflow_id"""
    state = WorkflowState(
        workflow_id=f"wf_test_status_{stage}_{stage_state}",
        topic="测试主题",
        max_items=2,
        dimensions=["维度1"],
    )
    state.current_stage = stage
    state.stage_state = stage_state
    state.stage_output = stage_output
    state.stage_history = [
        {"stage": stage, "decision": "reject", "timestamp": "t"}
        for _ in range(history_len)
    ]
    workflow_service._workflows[state.workflow_id] = state
    return state.workflow_id


@pytest.mark.asyncio
async def test_status_endpoint_404_when_workflow_not_found(async_db: AsyncSession):
    """/status 不存在的 workflow_id 应返 404"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/workflow/wf_nonexistent_xyz/status")
    assert res.status_code == 404
    assert "not found" in res.text.lower()


@pytest.mark.asyncio
async def test_status_endpoint_running_returns_sse_url(async_db: AsyncSession):
    """running 状态时,sse_url 字段应指向对应 stage 的流 URL"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state("cleaning", StageState.RUNNING)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/workflow/{wf_id}/status")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["stage"] == "cleaning"
    assert body["stage_state"] == StageState.RUNNING
    assert body["sse_url"] == f"/api/v1/workflow/{wf_id}/stream-cleaning"


@pytest.mark.asyncio
async def test_status_endpoint_awaiting_confirmation_has_no_sse_url(async_db: AsyncSession):
    """awaiting_confirmation 状态时,sse_url 应为 null(下一步是 confirm,不是启动 SSE)"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state(
        "collecting",
        StageState.AWAITING_CONFIRMATION,
        stage_output={"stage": "collecting", "sources": [], "item_count": 0, "warning": ""},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/workflow/{wf_id}/status")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["stage_state"] == StageState.AWAITING_CONFIRMATION
    # 弹窗恢复用,sse_url 在 awaiting_confirmation 时无意义
    assert body["sse_url"] is None
    # stage_output 应透传
    assert body["stage_output"] is not None
    assert body["stage_output"]["stage"] == "collecting"


@pytest.mark.asyncio
async def test_status_endpoint_returns_stage_history_length(async_db: AsyncSession):
    """stage_history_length 字段应正确反映 history 长度"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state(
        "analyzing",
        StageState.AWAITING_CONFIRMATION,
        history_len=2,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/workflow/{wf_id}/status")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["stage_history_length"] == 2


@pytest.mark.asyncio
async def test_status_endpoint_all_4_stages_sse_url(async_db: AsyncSession):
    """验证 4 个 stage 都能正确生成 sse_url"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    for stage in ["collecting", "cleaning", "analyzing", "reporting"]:
        wf_id = _build_workflow_in_state(stage, StageState.RUNNING)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get(f"/api/v1/workflow/{wf_id}/status")
        assert res.status_code == 200, f"{stage} should be 200"
        body = res.json()["data"]
        assert body["sse_url"] == f"/api/v1/workflow/{wf_id}/stream-{stage}", \
            f"{stage} sse_url mismatch"


# 注:401 由全局 auth 依赖处理,与现有 confirm 端点测试一样不直接测(需要伪造 token)
