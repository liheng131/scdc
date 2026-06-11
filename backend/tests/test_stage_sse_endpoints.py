"""
Spec 2 集成测试 - 3 个 stage-specific SSE 端点

验证:
- /stream-cleaning, /stream-analyzing, /stream-reporting 端点存在
- 错误时返 SSE error 事件
"""
import pytest
from fastapi.testclient import TestClient
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
        username="test_sse_user",
        email="test_sse@example.com",
        password_hash="hash",
        role="admin",
        status="active",
    )


def _build_workflow_in_state(stage: str, stage_state: str) -> str:
    state = WorkflowState(
        workflow_id=f"wf_test_sse_{stage}_{stage_state}",
        topic="测试主题",
        max_items=2,
        dimensions=["维度1"],
    )
    state.current_stage = stage
    state.stage_state = stage_state
    workflow_service._workflows[state.workflow_id] = state
    return state.workflow_id


def _read_sse_chunks(client, url, max_chunks=2, timeout=3.0):
    """同步读 SSE 流的最多 max_chunks 个 chunk(快速返回避免等流关闭)"""
    chunks = []
    with client.stream("GET", url, timeout=timeout) as r:
        for line in r.iter_lines():
            chunks.append(line)
            if len(chunks) >= max_chunks * 6:  # 6 行 ≈ 1 个 event
                break
    return "\n".join(chunks)


# ========== 404 测试（workflow 不存在）============

def test_stage_sse_endpoint_returns_error_event_when_workflow_not_found():
    """/stream-{stage} 不存在的 workflow_id 应返 SSE error 事件"""
    # 用依赖覆盖
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_active_user_sse] = lambda: _create_test_user()

    with TestClient(app) as client:
        for stage in ["cleaning", "analyzing", "reporting"]:
            text = _read_sse_chunks(client, f"/api/v1/workflow/wf_nonexistent_xyz/stream-{stage}")
            assert "error" in text.lower(), f"{stage} should yield error event, got: {text}"
            assert "not found" in text.lower(), f"{stage} error msg should mention 'not found'"


# ========== 409 测试（错配的 stage）============

def test_stage_sse_endpoint_error_on_mismatched_stage():
    """SSE 端点要求的 stage 与 workflow.current_stage 不匹配时返错误事件"""
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_active_user_sse] = lambda: _create_test_user()

    with TestClient(app) as client:
        # workflow.current_stage = 'collecting' 但请求 stream-cleaning
        wf_id = _build_workflow_in_state("collecting", StageState.RUNNING)
        text = _read_sse_chunks(client, f"/api/v1/workflow/{wf_id}/stream-cleaning")
        assert "error" in text.lower()
        assert "current_stage" in text.lower() or "'collecting'" in text


# ========== 409 测试（非 running 状态）============

def test_stage_sse_endpoint_error_when_not_running():
    """SSE 端点要求 workflow.stage_state == 'running',否则返错误事件"""
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_active_user_sse] = lambda: _create_test_user()

    with TestClient(app) as client:
        # current_stage='cleaning' 匹配 endpoint,但 stage_state 是 AWAITING
        wf_id = _build_workflow_in_state("cleaning", StageState.AWAITING_CONFIRMATION)
        text = _read_sse_chunks(client, f"/api/v1/workflow/{wf_id}/stream-cleaning")
        assert "error" in text.lower()
        assert "running" in text.lower() or "state" in text.lower()


# ========== 健康检查：所有 3 端点都注册了 ==========

def test_all_3_stage_sse_endpoints_registered():
    """FastAPI app 应注册 3 个新 SSE 端点"""
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    for stage in ["cleaning", "analyzing", "reporting"]:
        expected = f"/api/v1/workflow/{{workflow_id}}/stream-{stage}"
        assert expected in paths, f"Missing endpoint: {expected}"
