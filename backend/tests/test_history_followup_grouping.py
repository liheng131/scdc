"""
回归测试：历史追问聚合 spec。

背景：用户反馈一个对话里追问多次后，刷新历史记录会让一个对话被拆成多个独立对话。
根因是 follow-up 创建的新 workflow_run 与父 workflow 没有父子关联。
本测试验证：
1. create_workflow 接受 parent_workflow_id 并持久化
2. FollowUpRequest schema 接受 parent_workflow_id
3. get_history 返回分组结构(顶层 + 内嵌 children)
4. 孤儿追问(父被删除)按顶层处理
"""
import pytest
import pytest_asyncio
from app.services.workflow import workflow_service
from app.api.routes.workflow import FollowUpRequest
from app.core import db as core_db
from app.models.workflow_run import WorkflowRun
from sqlalchemy import delete, select
import uuid


def _unique_id() -> str:
    return uuid.uuid4().hex[:8]


@pytest_asyncio.fixture(autouse=True)
async def reset_engine_pool():
    """每个测试前/后 dispose engine,避免连接池残留 asyncpg 状态。"""
    await core_db.engine.dispose()
    yield
    await core_db.engine.dispose()


@pytest.mark.asyncio
async def test_create_workflow_with_parent_workflow_id_persists():
    """create_workflow 接受 parent_workflow_id 并写入 DB 行。"""
    parent = await workflow_service.create_workflow(
        topic=f"test_parent_{_unique_id()}", max_items=0, initial_stage=None
    )
    child = await workflow_service.create_workflow(
        topic=f"test_child_{_unique_id()}",
        max_items=0,
        initial_stage=None,
        parent_workflow_id=parent.workflow_id,
    )
    # 从 DB 读回,确认 parent_workflow_id 已持久化
    async with core_db.async_session_factory() as session:
        result = await session.execute(
            select(WorkflowRun).where(WorkflowRun.workflow_id == child.workflow_id)
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.parent_workflow_id == parent.workflow_id


@pytest.mark.asyncio
async def test_create_workflow_without_parent_persists_null():
    """不传 parent_workflow_id → DB 行的 parent_workflow_id 为 NULL。"""
    state = await workflow_service.create_workflow(
        topic=f"test_no_parent_{_unique_id()}", max_items=0, initial_stage=None
    )
    async with core_db.async_session_factory() as session:
        result = await session.execute(
            select(WorkflowRun).where(WorkflowRun.workflow_id == state.workflow_id)
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.parent_workflow_id is None


def test_follow_up_request_schema_accepts_parent_workflow_id():
    """FollowUpRequest Pydantic 模型接受可选 parent_workflow_id。"""
    req1 = FollowUpRequest(message="hi", parent_workflow_id="wf_abc")
    assert req1.parent_workflow_id == "wf_abc"
    req2 = FollowUpRequest(message="hi")
    assert req2.parent_workflow_id is None


@pytest.mark.asyncio
async def test_get_history_groups_parent_and_children():
    """get_history 把 1 父 + 2 子折叠为 1 个顶层元素,内嵌 2 个 children。"""
    suffix = _unique_id()
    parent = await workflow_service.create_workflow(
        topic=f"test_grouping_parent_{suffix}", max_items=0, initial_stage=None
    )
    child1 = await workflow_service.create_workflow(
        topic=f"test_grouping_child1_{suffix}",
        max_items=0,
        initial_stage=None,
        parent_workflow_id=parent.workflow_id,
    )
    child2 = await workflow_service.create_workflow(
        topic=f"test_grouping_child2_{suffix}",
        max_items=0,
        initial_stage=None,
        parent_workflow_id=parent.workflow_id,
    )

    history = await workflow_service.get_history()
    found = next((x for x in history if x["workflow_id"] == parent.workflow_id), None)
    assert found is not None, f"parent {parent.workflow_id} not in history"
    assert "children" in found
    child_ids = {c["workflow_id"] for c in found["children"]}
    assert child1.workflow_id in child_ids
    assert child2.workflow_id in child_ids
    assert len(found["children"]) == 2


@pytest.mark.asyncio
async def test_get_history_orphan_promoted_to_top_level():
    """孤儿追问(父被删除)按顶层处理。"""
    suffix = _unique_id()
    parent = await workflow_service.create_workflow(
        topic=f"test_orphan_parent_{suffix}", max_items=0, initial_stage=None
    )
    child = await workflow_service.create_workflow(
        topic=f"test_orphan_child_{suffix}",
        max_items=0,
        initial_stage=None,
        parent_workflow_id=parent.workflow_id,
    )
    # 删除父
    async with core_db.async_session_factory() as session:
        await session.execute(delete(WorkflowRun).where(WorkflowRun.workflow_id == parent.workflow_id))
        await session.commit()

    history = await workflow_service.get_history()
    found = next((x for x in history if x["workflow_id"] == child.workflow_id), None)
    assert found is not None, f"orphan child {child.workflow_id} should be top-level"
    assert found["children"] == []
