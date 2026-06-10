"""
Phase 2 (Spec 1) 集成测试 - /api/v1/workflow/{id}/confirm 端点

通过 FastAPI TestClient 直接调端点,验证:
- 状态码、响应结构、错误处理
- 状态机正确流转
- stage_history 正确返回
- sse_url 字段正确生成

注意:不依赖 CollectorAgent 真实调用,通过 monkeypatch stub 掉 _persist_stage_update 与
预先 set state.stage_state 来模拟"已 awaiting_confirmation"状态。
"""
import json
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.db import get_db
from app.api.deps import get_current_active_user, get_current_active_user_sse
from app.models.user import User
from app.services.workflow import (
    workflow_service,
    StageState,
    STAGE_SEQUENCE,
)


async def _noop_persist(state):
    return None


def _create_test_user() -> User:
    return User(
        id=999,
        username="test_confirm_user",
        email="test_confirm@example.com",
        password_hash="hash",
        role="admin",
        status="active",
    )


def _build_workflow_in_state(stage: str, stage_state: str) -> str:
    """手动把 workflow_service 内部缓存填入一个测试 workflow,返回 workflow_id"""
    from app.services.workflow import WorkflowState
    state = WorkflowState(
        workflow_id=f"wf_test_{stage}_{stage_state}",
        topic="测试主题",
        max_items=2,
        dimensions=["维度1"],
    )
    state.current_stage = stage
    state.stage_state = stage_state
    state.stage_history = []
    workflow_service._workflows[state.workflow_id] = state
    return state.workflow_id


@pytest.mark.asyncio
async def test_confirm_endpoint_404_when_workflow_not_found(async_db: AsyncSession):
    """/confirm 不存在的 workflow_id 应返 404"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/workflow/wf_nonexistent_xyz/confirm",
            json={"decision": "accept"},
        )
    assert res.status_code == 404
    assert "not found" in res.text.lower()


@pytest.mark.asyncio
async def test_confirm_endpoint_409_when_not_awaiting(async_db: AsyncSession, monkeypatch):
    """/confirm 在 running 状态时返回 409"""
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)

    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state("collecting", StageState.RUNNING)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/api/v1/workflow/{wf_id}/confirm",
            json={"decision": "accept"},
        )

    assert res.status_code == 409
    body = res.json()
    assert "awaiting_confirmation" in body["detail"]
    # 清理
    workflow_service._workflows.pop(wf_id, None)


@pytest.mark.asyncio
async def test_confirm_endpoint_422_invalid_decision(async_db: AsyncSession, monkeypatch):
    """/confirm 非法 decision 返 422"""
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)

    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state("collecting", StageState.AWAITING_CONFIRMATION)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/api/v1/workflow/{wf_id}/confirm",
            json={"decision": "pause"},
        )

    # FastAPI 的 Literal["accept","reject"] 在请求体里直接走 Pydantic 校验
    # 422 而不是 200(因为 Pydantic 不允许 "pause")
    assert res.status_code == 422
    workflow_service._workflows.pop(wf_id, None)


@pytest.mark.asyncio
async def test_confirm_endpoint_accept_returns_cleaning_sse_url(async_db: AsyncSession, monkeypatch):
    """accept 成功 → next_stage=cleaning, sse_url 指 /stream"""
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)

    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state("collecting", StageState.AWAITING_CONFIRMATION)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/api/v1/workflow/{wf_id}/confirm",
            json={"decision": "accept"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    d = body["data"]
    assert d["workflow_id"] == wf_id
    assert d["stage"] == "cleaning"           # current_stage 已推进
    assert d["next_stage"] == "cleaning"
    assert d["stage_state"] == StageState.RUNNING
    assert d["sse_url"] == f"/api/v1/workflow/{wf_id}/stream"
    assert d["stage_history_length"] == 1

    workflow_service._workflows.pop(wf_id, None)


@pytest.mark.asyncio
async def test_confirm_endpoint_reject_returns_collecting_sse_url(async_db: AsyncSession, monkeypatch):
    """reject 成功 → next_stage=collecting, sse_url 指 /stream-collecting"""
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)

    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state("collecting", StageState.AWAITING_CONFIRMATION)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/api/v1/workflow/{wf_id}/confirm",
            json={
                "decision": "reject",
                "user_edits": {
                    "extra_urls": ["https://example.com/a"],
                    "extra_keywords": ["关键词X"],
                },
                "user_feedback": "上次采得不全",
            },
        )

    assert res.status_code == 200
    body = res.json()
    d = body["data"]
    assert d["next_stage"] == "collecting"
    assert d["stage_state"] == StageState.RUNNING
    assert d["sse_url"] == f"/api/v1/workflow/{wf_id}/stream-collecting"
    assert d["stage_history_length"] == 1

    # 验证 stage_history 内容
    state = workflow_service._workflows[wf_id]
    h = state.stage_history[0]
    assert h["decision"] == "reject"
    assert h["user_feedback"] == "上次采得不全"
    assert h["user_edits"]["extra_keywords"] == ["关键词X"]
    # topic 应已被合并
    assert "https://example.com/a" in state.topic
    assert "关键词X" in state.topic
    assert "上次采得不全" in state.topic

    workflow_service._workflows.pop(wf_id, None)


@pytest.mark.asyncio
async def test_confirm_endpoint_reject_exceeds_max_retry_returns_429(async_db: AsyncSession, monkeypatch):
    """reject 次数 >= MAX_RETRY_PER_STAGE 时返 429"""
    from app.services.workflow import MAX_RETRY_PER_STAGE
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)

    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user] = lambda: _create_test_user()

    # 准备一个已经重试 MAX_RETRY_PER_STAGE 次的 workflow
    from app.services.workflow import WorkflowState
    state = WorkflowState(
        workflow_id="wf_test_max_retry",
        topic="t", max_items=2, dimensions=[],
    )
    state.current_stage = "collecting"
    state.stage_state = StageState.AWAITING_CONFIRMATION
    state.stage_history = [
        {"stage": "collecting", "decision": "reject", "timestamp": "x"}
        for _ in range(MAX_RETRY_PER_STAGE)
    ]
    workflow_service._workflows[state.workflow_id] = state

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/api/v1/workflow/{state.workflow_id}/confirm",
            json={"decision": "reject"},
        )

    assert res.status_code == 429
    assert "重试次数过多" in res.json()["detail"]

    workflow_service._workflows.pop(state.workflow_id, None)


@pytest.mark.asyncio
async def test_stream_collecting_endpoint_404_when_workflow_not_found(async_db: AsyncSession):
    """/stream-collecting 不存在的 workflow → SSE error 事件"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user_sse] = lambda: _create_test_user()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/workflow/wf_nonexistent_xyz/stream-collecting",
        )

    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
    body = res.text
    assert "event: error" in body
    assert "not found" in body.lower()


@pytest.mark.asyncio
async def test_stream_collecting_endpoint_409_when_not_running(async_db: AsyncSession):
    """/stream-collecting 在 awaiting_confirmation 状态应返 SSE error"""
    app.dependency_overrides[get_db] = lambda: async_db
    app.dependency_overrides[get_current_active_user_sse] = lambda: _create_test_user()

    wf_id = _build_workflow_in_state("collecting", StageState.AWAITING_CONFIRMATION)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/workflow/{wf_id}/stream-collecting")

    assert res.status_code == 200
    body = res.text
    assert "event: error" in body
    assert "running" in body.lower()
    workflow_service._workflows.pop(wf_id, None)
