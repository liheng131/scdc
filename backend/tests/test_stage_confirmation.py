"""
Phase 2 (Spec 1) 单元测试 - confirm_stage 状态机

覆盖以下场景：
- 状态非 awaiting_confirmation 时 confirm → 409
- decision 非法值 → 422
- reject 重试次数超过 MAX_RETRY_PER_STAGE → 429
- accept 成功流转到下一阶段,stage_state 变为 running
- reject 成功重跑当前阶段,user_edits/user_feedback 合并到 topic
- stage_history 正确记录每次操作
- accept 在 reporting 阶段(理论兜底)→ stage_state=completed, next_stage=None
"""
import pytest
from fastapi import HTTPException

from app.services.workflow import (
    workflow_service,
    WorkflowState,
    StageState,
    STAGE_SEQUENCE,
    MAX_RETRY_PER_STAGE,
)


async def _noop_persist(state):
    """Stub 异步持久化,避免 DB IO"""
    return None


@pytest.fixture
def patch_persist(monkeypatch):
    """monkeypatch _persist_stage_update 为无操作"""
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)


def make_state(stage: str = "collecting", stage_state: str = StageState.AWAITING_CONFIRMATION,
               topic: str = "测试主题", history: list = None) -> WorkflowState:
    """构造一个指定状态的 WorkflowState(不依赖 DB / 外部服务)"""
    state = WorkflowState(
        workflow_id=f"ut_{id(object())}"[:8],
        topic=topic,
        max_items=3,
        dimensions=["维度1"],
    )
    state.current_stage = stage
    state.stage_state = stage_state
    state.stage_history = history or []
    return state


@pytest.mark.asyncio
async def test_confirm_stage_non_awaiting_returns_409(patch_persist):
    """状态不是 awaiting_confirmation 时,confirm 应抛 409"""
    state = make_state(stage="collecting", stage_state=StageState.RUNNING)
    with pytest.raises(HTTPException) as exc:
        await workflow_service.confirm_stage(state, decision="accept")
    assert exc.value.status_code == 409
    assert "awaiting_confirmation" in exc.value.detail


@pytest.mark.asyncio
async def test_confirm_stage_invalid_decision_returns_422(patch_persist):
    """非法 decision 值应抛 422"""
    state = make_state(stage="collecting", stage_state=StageState.AWAITING_CONFIRMATION)
    with pytest.raises(HTTPException) as exc:
        await workflow_service.confirm_stage(state, decision="pause")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_confirm_stage_reject_exceeds_max_retry_returns_429(patch_persist):
    """reject 次数 >= MAX_RETRY_PER_STAGE 时应抛 429"""
    history = [
        {"stage": "collecting", "decision": "reject", "timestamp": "2026-06-10T10:00:00Z"}
        for _ in range(MAX_RETRY_PER_STAGE)
    ]
    state = make_state(
        stage="collecting",
        stage_state=StageState.AWAITING_CONFIRMATION,
        history=history,
    )
    with pytest.raises(HTTPException) as exc:
        await workflow_service.confirm_stage(state, decision="reject")
    assert exc.value.status_code == 429
    assert "重试次数过多" in exc.value.detail


@pytest.mark.asyncio
async def test_confirm_stage_accept_advances_to_next_stage(patch_persist):
    """accept 成功 → stage_state=running, current_stage 推进, stage_output 清空"""
    state = make_state(stage="collecting", stage_state=StageState.AWAITING_CONFIRMATION)
    state.stage_output = {"sources": [{"x": 1}]}

    result = await workflow_service.confirm_stage(state, decision="accept")

    assert result["next_stage"] == "cleaning"
    assert result["stage_state"] == StageState.RUNNING
    assert state.current_stage == "cleaning"
    assert state.stage_state == StageState.RUNNING
    assert state.stage_output is None, "accept 后应清空 stage_output"
    assert len(state.stage_history) == 1
    assert state.stage_history[0]["decision"] == "accept"
    assert state.stage_history[0]["stage"] == "collecting"


@pytest.mark.asyncio
async def test_confirm_stage_accept_in_reporting_completes(patch_persist):
    """accept 在 reporting 阶段(兜底)→ stage_state=completed, next_stage=None"""
    state = make_state(stage="reporting", stage_state=StageState.AWAITING_CONFIRMATION)
    result = await workflow_service.confirm_stage(state, decision="accept")
    assert result["next_stage"] is None
    assert result["stage_state"] == StageState.COMPLETED
    assert state.stage_state == StageState.COMPLETED


@pytest.mark.asyncio
async def test_confirm_stage_reject_merges_user_edits_into_topic(patch_persist):
    """reject 成功 → stage_state=running, user_edits 合并到 topic, 不切换 stage"""
    state = make_state(
        stage="collecting",
        stage_state=StageState.AWAITING_CONFIRMATION,
        topic="原始主题",
    )

    result = await workflow_service.confirm_stage(
        state,
        decision="reject",
        user_edits={
            "extra_urls": ["https://example.com/a", "https://example.com/b"],
            "extra_keywords": ["关键词A", "关键词B"],
        },
        user_feedback="请补采国内信源",
    )

    assert result["next_stage"] == "collecting"
    assert result["stage_state"] == StageState.RUNNING
    assert state.current_stage == "collecting", "reject 不应切换 current_stage"
    assert state.stage_state == StageState.RUNNING
    assert "原始主题" in state.topic
    assert "https://example.com/a" in state.topic
    assert "https://example.com/b" in state.topic
    assert "关键词A" in state.topic
    assert "请补采国内信源" in state.topic
    assert len(state.stage_history) == 1
    h = state.stage_history[0]
    assert h["decision"] == "reject"
    assert h["user_feedback"] == "请补采国内信源"
    assert h["user_edits"]["extra_keywords"] == ["关键词A", "关键词B"]


@pytest.mark.asyncio
async def test_confirm_stage_reject_empty_user_input_keeps_topic(patch_persist):
    """reject 但 user_edits/feedback 为空 → topic 不变, 仅记录 history"""
    state = make_state(
        stage="collecting",
        stage_state=StageState.AWAITING_CONFIRMATION,
        topic="原始主题",
    )

    result = await workflow_service.confirm_stage(state, decision="reject")

    assert result["next_stage"] == "collecting"
    assert state.topic == "原始主题", "空 user_edits/feedback 时 topic 不变"
    assert len(state.stage_history) == 1
    assert state.stage_history[0]["decision"] == "reject"
    assert state.stage_history[0]["user_edits"] is None
    assert state.stage_history[0]["user_feedback"] is None


@pytest.mark.asyncio
async def test_confirm_stage_history_grows_correctly(patch_persist):
    """连续操作后 stage_history 累加正确"""
    state = make_state(stage="collecting", stage_state=StageState.AWAITING_CONFIRMATION)

    # reject 1
    await workflow_service.confirm_stage(state, decision="reject", user_feedback="第一次反馈")
    # reject 2
    state.stage_state = StageState.AWAITING_CONFIRMATION  # 模拟新一次确认
    await workflow_service.confirm_stage(state, decision="reject", user_feedback="第二次反馈")
    # accept
    state.stage_state = StageState.AWAITING_CONFIRMATION
    result = await workflow_service.confirm_stage(state, decision="accept")

    assert len(state.stage_history) == 3
    assert state.stage_history[0]["decision"] == "reject"
    assert state.stage_history[0]["user_feedback"] == "第一次反馈"
    assert state.stage_history[1]["user_feedback"] == "第二次反馈"
    assert state.stage_history[2]["decision"] == "accept"
    assert state.current_stage == "cleaning"
    assert result["next_stage"] == "cleaning"
