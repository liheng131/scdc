"""
Spec 2 单元测试 - confirm_stage skip 决策

覆盖：
- skip 合法：进入下一阶段,stage_state=running
- skip 等价 accept 但 stage_history 记录 decision='skip'
- skip 不计重试：连续 skip 不会触发 429
- skip 不接受 user_edits/user_feedback(忽略,不合并到 topic)
- skip 在 reporting 阶段(理论兜底)→ stage_state=completed
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
    return None


@pytest.fixture
def patch_persist(monkeypatch):
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)


def make_state(stage: str = "collecting", stage_state: str = StageState.AWAITING_CONFIRMATION,
               topic: str = "测试主题", history: list = None) -> WorkflowState:
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
async def test_skip_advances_to_next_stage(patch_persist):
    """skip 应推进到下一阶段,stage_state=running"""
    state = make_state(stage="collecting")
    result = await workflow_service.confirm_stage(state, decision="skip")
    assert state.current_stage == "cleaning"
    assert state.stage_state == StageState.RUNNING
    assert result["next_stage"] == "cleaning"


@pytest.mark.asyncio
async def test_skip_records_history_with_decision_skip(patch_persist):
    """skip 在 stage_history 中记录 decision='skip'"""
    state = make_state(stage="cleaning")
    await workflow_service.confirm_stage(state, decision="skip")
    assert len(state.stage_history) == 1
    assert state.stage_history[0]["decision"] == "skip"
    assert state.stage_history[0]["stage"] == "cleaning"


@pytest.mark.asyncio
async def test_skip_does_not_count_as_retry(patch_persist):
    """skip 不计入重试,连续多次 skip 不会触发 429"""
    # 制造 MAX_RETRY_PER_STAGE 条 skip history
    history = [
        {"stage": "collecting", "decision": "skip", "timestamp": "2026-06-10T10:00:00Z"}
        for _ in range(MAX_RETRY_PER_STAGE)
    ]
    state = make_state(stage="collecting", history=history)
    # 现在再 skip 一次,应该不会 429
    result = await workflow_service.confirm_stage(state, decision="skip")
    assert state.current_stage == "cleaning"


@pytest.mark.asyncio
async def test_skip_ignores_user_edits_and_feedback(patch_persist):
    """skip 时 user_edits 和 user_feedback 不应被合并到 topic（Spec 2 约定）"""
    state = make_state(stage="collecting", topic="原始主题")
    original_topic = state.topic
    await workflow_service.confirm_stage(
        state, decision="skip",
        user_edits={"extra_urls": ["http://should-be-ignored.com"]},
        user_feedback="should-be-ignored",
    )
    # topic 不应被修改（核心约束：skip 不重跑,不消费反馈）
    assert state.topic == original_topic
    assert "should-be-ignored" not in state.topic
    assert "http://should-be-ignored.com" not in state.topic


@pytest.mark.asyncio
async def test_skip_on_reporting_completes_workflow(patch_persist):
    """skip 在 reporting 阶段(理论兜底)→ stage_state=completed, next_stage=None"""
    state = make_state(stage="reporting")
    result = await workflow_service.confirm_stage(state, decision="skip")
    assert state.stage_state == StageState.COMPLETED
    assert result["next_stage"] is None


@pytest.mark.asyncio
async def test_skip_clears_stage_output(patch_persist):
    """skip 应清空 stage_output(为下一阶段准备)"""
    state = make_state(stage="collecting")
    state.stage_output = {"stage": "collecting", "sources": []}
    await workflow_service.confirm_stage(state, decision="skip")
    assert state.stage_output is None


@pytest.mark.asyncio
async def test_mix_skip_and_reject_skip_does_not_consume_retry_quota(patch_persist):
    """交替使用 skip 和 reject：skip 不消耗 reject 的 3 次额度"""
    # 先做 2 次 reject,2 次 skip,再 1 次 reject 应该仍允许
    history = [
        {"stage": "collecting", "decision": "reject", "timestamp": "t"},
        {"stage": "collecting", "decision": "skip", "timestamp": "t"},
        {"stage": "collecting", "decision": "reject", "timestamp": "t"},
        {"stage": "collecting", "decision": "skip", "timestamp": "t"},
    ]
    state = make_state(stage="collecting", history=history)
    # 2 reject 已经用了 2 次,还有 1 次 reject 额度
    # 第 3 次 reject 应该成功
    result = await workflow_service.confirm_stage(
        state, decision="reject", user_feedback="再来"
    )
    assert state.stage_state == StageState.RUNNING
    # 现在 history 有 3 个 reject,如果再 reject 应触发 429
    # 需要先重置 stage_state 为 awaiting_confirmation
    state.stage_state = StageState.AWAITING_CONFIRMATION
    with pytest.raises(HTTPException) as exc:
        await workflow_service.confirm_stage(
            state, decision="reject", user_feedback="再来"
        )
    assert exc.value.status_code == 429
