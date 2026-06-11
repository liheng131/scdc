"""
Spec 2 单元测试 - user_edits 在 4 阶段的合并与 schema 验证

覆盖：
- reject 携带 user_edits 时，cleaning/analyzing/reporting 阶段 user_edits
  可以包含扩展字段（removed_item_ids / removed_insight_ids / edited_sections 等）
- 通用 extra_urls/extra_keywords 总是被合并到 topic
- user_feedback 总是被合并到 topic
- ConfirmStageRequest Pydantic schema 接受 4 阶段 user_edits 结构
"""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.workflow import (
    workflow_service,
    WorkflowState,
    StageState,
    STAGE_SEQUENCE,
    MAX_RETRY_PER_STAGE,
)
from app.api.routes.workflow import ConfirmStageRequest


# ========== Fixtures ==========

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


# ========== Pydantic schema 验证 ==========

def test_confirm_stage_request_accepts_skip_decision():
    """decision='skip' 是合法值"""
    req = ConfirmStageRequest(decision="skip")
    assert req.decision == "skip"


def test_confirm_stage_request_accepts_cleaning_user_edits():
    """cleaning 阶段 user_edits 可带 removed_item_ids + min_content_length + language"""
    req = ConfirmStageRequest(
        decision="reject",
        user_edits={
            "extra_urls": ["http://a.com"],
            "extra_keywords": ["kw1"],
            "removed_item_ids": ["item-1", "item-2"],
            "min_content_length": 200,
            "language": "zh",
        },
        user_feedback="多保留国内信源",
    )
    assert req.user_edits["removed_item_ids"] == ["item-1", "item-2"]
    assert req.user_edits["min_content_length"] == 200
    assert req.user_edits["language"] == "zh"


def test_confirm_stage_request_accepts_analyzing_user_edits():
    """analyzing 阶段 user_edits 可带 removed_insight_ids + custom_dimensions"""
    req = ConfirmStageRequest(
        decision="reject",
        user_edits={
            "removed_insight_ids": ["ins-1"],
            "custom_dimensions": ["新维度"],
        },
    )
    assert req.user_edits["removed_insight_ids"] == ["ins-1"]
    assert req.user_edits["custom_dimensions"] == ["新维度"]


def test_confirm_stage_request_accepts_reporting_user_edits():
    """reporting 阶段 user_edits 可带 edited_sections + removed_section_ids + appended_sections"""
    req = ConfirmStageRequest(
        decision="reject",
        user_edits={
            "edited_sections": {"执行摘要": "改写后的摘要"},
            "removed_section_ids": ["sec-2"],
            "appended_sections": ["风险提示"],
        },
    )
    assert req.user_edits["edited_sections"]["执行摘要"] == "改写后的摘要"


def test_confirm_stage_request_rejects_invalid_decision():
    """非法 decision 值应被 Pydantic 拒绝"""
    with pytest.raises(ValidationError):
        ConfirmStageRequest(decision="pause")


# ========== reject 合并逻辑 ==========

@pytest.mark.asyncio
async def test_reject_merges_extra_urls_into_topic(patch_persist):
    """reject 携带 extra_urls 应合并到 topic"""
    state = make_state(stage="collecting")
    user_edits = {"extra_urls": ["http://a.com", "http://b.com"]}
    await workflow_service.confirm_stage(
        state, decision="reject", user_edits=user_edits
    )
    assert "http://a.com" in state.topic
    assert "http://b.com" in state.topic
    assert "补充URL" in state.topic


@pytest.mark.asyncio
async def test_reject_merges_extra_keywords_into_topic(patch_persist):
    """reject 携带 extra_keywords 应合并到 topic"""
    state = make_state(stage="cleaning")
    user_edits = {"extra_keywords": ["AI制药", "临床试验"]}
    await workflow_service.confirm_stage(
        state, decision="reject", user_edits=user_edits
    )
    assert "AI制药" in state.topic
    assert "临床试验" in state.topic


@pytest.mark.asyncio
async def test_reject_merges_user_feedback_into_topic(patch_persist):
    """reject 携带 user_feedback 应合并到 topic"""
    state = make_state(stage="analyzing")
    await workflow_service.confirm_stage(
        state, decision="reject", user_feedback="重点关注国内厂商"
    )
    assert "重点关注国内厂商" in state.topic
    assert "用户反馈" in state.topic


@pytest.mark.asyncio
async def test_reject_with_cleaning_extensions_keeps_stage_state_running(patch_persist):
    """reject 时虽然带 cleaning 扩展字段（不会用到），但 state 应被正确流转"""
    state = make_state(stage="cleaning")
    user_edits = {
        "extra_urls": ["http://a.com"],
        "removed_item_ids": ["item-1"],  # cleaning 扩展
        "min_content_length": 300,
    }
    result = await workflow_service.confirm_stage(
        state, decision="reject", user_edits=user_edits
    )
    # reject 后 stage_state 仍为 running, current_stage 不变
    assert state.stage_state == StageState.RUNNING
    assert state.current_stage == "cleaning"
    assert result["next_stage"] == "cleaning"


@pytest.mark.asyncio
async def test_reject_with_reporting_extensions_appended_sections(patch_persist):
    """reporting 阶段 reject 带扩展字段也能正常流转"""
    state = make_state(stage="reporting")
    user_edits = {
        "edited_sections": {"执行摘要": "改写"},
        "appended_sections": ["风险提示"],
    }
    result = await workflow_service.confirm_stage(
        state, decision="reject", user_edits=user_edits
    )
    # reporting 是最后阶段,reject 应该重跑 reporting
    assert state.stage_state == StageState.RUNNING
    assert state.current_stage == "reporting"
    assert result["next_stage"] == "reporting"


# ========== stage_history 记录 ==========

@pytest.mark.asyncio
async def test_reject_records_history_with_all_fields(patch_persist):
    """reject 时 stage_history 应记录 decision/user_edits/user_feedback/timestamp"""
    state = make_state(stage="cleaning")
    user_edits = {"extra_urls": ["http://a.com"]}
    await workflow_service.confirm_stage(
        state, decision="reject",
        user_edits=user_edits,
        user_feedback="测试反馈"
    )
    assert len(state.stage_history) == 1
    entry = state.stage_history[0]
    assert entry["stage"] == "cleaning"
    assert entry["decision"] == "reject"
    assert entry["user_edits"] == user_edits
    assert entry["user_feedback"] == "测试反馈"
    assert "timestamp" in entry
