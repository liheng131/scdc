"""
Spec 2 单元测试 - 通用 stage runner + dispatch

覆盖：
- run_stage_only_stream 对 4 阶段 dispatch 正确
- _run_single_stage 派发到正确 helper
- _run_X_stage 各 helper 输出 schema 正确
- 4 阶段都设 stage_state='awaiting_confirmation' 并写 stage_output
- 错误处理：agent 失败 → stage_state='failed' + stage_error 事件
- unknown stage 抛 ValueError
"""
import pytest
from contextlib import asynccontextmanager

from app.services.workflow import (
    workflow_service,
    WorkflowState,
    StageState,
    STAGE_SEQUENCE,
)


# ========== Fixtures ==========

async def _noop_persist(state):
    return None


@pytest.fixture
def patch_persist(monkeypatch):
    monkeypatch.setattr(workflow_service, "_persist_stage_update", _noop_persist)


def make_state(stage: str = "collecting", stage_state: str = StageState.RUNNING,
               topic: str = "测试主题", stages: dict = None) -> WorkflowState:
    state = WorkflowState(
        workflow_id=f"ut_{id(object())}"[:8],
        topic=topic,
        max_items=3,
        dimensions=["维度1"],
    )
    state.current_stage = stage
    state.stage_state = stage_state
    state.stages = stages or {}
    return state


@asynccontextmanager
async def _collect_stream(state, stage):
    """消费 SSE 流,返所有事件名+data。"""
    events = []
    async for sse in workflow_service.run_stage_only_stream(state, stage):
        # sse 格式: 'event: <name>\ndata: <json>\n\n'
        lines = sse.strip().split("\n")
        evt_name = None
        evt_data = None
        for line in lines:
            if line.startswith("event: "):
                evt_name = line[7:].strip()
            elif line.startswith("data: "):
                import json
                evt_data = json.loads(line[6:])
        events.append((evt_name, evt_data))
    return events


# ========== 状态校验 ==========

@pytest.mark.asyncio
async def test_run_stage_only_stream_validates_state_must_be_running(patch_persist):
    """state.stage_state != 'running' 时抛 RuntimeError"""
    state = make_state(stage="collecting", stage_state=StageState.AWAITING_CONFIRMATION)
    with pytest.raises(RuntimeError, match="not in 'running' state"):
        async for _ in workflow_service.run_stage_only_stream(state, "collecting"):
            pass


@pytest.mark.asyncio
async def test_run_stage_only_stream_validates_current_stage_matches(patch_persist):
    """state.current_stage != stage 时抛 RuntimeError"""
    state = make_state(stage="cleaning", stage_state=StageState.RUNNING)
    with pytest.raises(RuntimeError, match="current_stage is 'cleaning'"):
        async for _ in workflow_service.run_stage_only_stream(state, "collecting"):
            pass


@pytest.mark.asyncio
async def test_run_stage_only_stream_rejects_unknown_stage(patch_persist):
    """未知 stage 名应抛 ValueError"""
    state = make_state(stage="invalid", stage_state=StageState.RUNNING)
    with pytest.raises(ValueError, match="Unknown stage"):
        async for _ in workflow_service.run_stage_only_stream(state, "invalid"):
            pass


# ========== Dispatch 测试（mock 4 个 agent）============

@pytest.mark.asyncio
async def test_run_stage_only_stream_collecting_dispatches_to_collector(monkeypatch, patch_persist):
    """collecting 阶段 → CollectorAgent"""
    state = make_state(stage="collecting", stage_state=StageState.RUNNING)

    # Mock CollectorAgent
    class FakeCollectorOutput:
        success = True
        warning = ""
        items = []

    class FakeCollectorAgent:
        async def execute(self, input):
            return FakeCollectorOutput()

    monkeypatch.setattr(
        "app.services.workflow.CollectorAgent",
        FakeCollectorAgent,
    )

    events = []
    async for sse in workflow_service.run_stage_only_stream(state, "collecting"):
        import json
        lines = sse.strip().split("\n")
        evt_name = None
        evt_data = None
        for line in lines:
            if line.startswith("event: "):
                evt_name = line[7:].strip()
            elif line.startswith("data: "):
                evt_data = json.loads(line[6:])
        events.append((evt_name, evt_data))

    event_names = [e[0] for e in events]
    assert "stage_start" in event_names
    assert "stage_complete" in event_names
    # 末尾 stage_complete 的 data 应包含 stage_output
    last_data = events[-1][1]
    assert last_data["stage"] == "collecting"
    assert last_data["stage_state"] == StageState.AWAITING_CONFIRMATION
    assert "stage_output" in last_data
    assert last_data["stage_output"]["stage"] == "collecting"
    assert "sources" in last_data["stage_output"]


@pytest.mark.asyncio
async def test_run_stage_only_stream_cleaning_requires_collecting_raw(monkeypatch, patch_persist):
    """cleaning 阶段没有 collecting._raw 时 → 错误事件 + stage_state=failed"""
    state = make_state(stage="cleaning", stage_state=StageState.RUNNING, stages={})

    class FakeCleanerAgent:
        async def execute(self, input):
            raise AssertionError("CleanerAgent should NOT be called when no raw items")

    monkeypatch.setattr("app.services.workflow.CleanerAgent", FakeCleanerAgent)

    events = []
    async for sse in workflow_service.run_stage_only_stream(state, "cleaning"):
        import json
        lines = sse.strip().split("\n")
        evt_name = None
        evt_data = None
        for line in lines:
            if line.startswith("event: "):
                evt_name = line[7:].strip()
            elif line.startswith("data: "):
                evt_data = json.loads(line[6:])
        events.append((evt_name, evt_data))

    event_names = [e[0] for e in events]
    assert "stage_error" in event_names
    last_data = events[-1][1]
    assert last_data["stage"] == "cleaning"
    assert state.stage_state == StageState.FAILED


@pytest.mark.asyncio
async def test_run_stage_only_stream_analyzing_requires_cleaning_raw(monkeypatch, patch_persist):
    """analyzing 阶段没有 cleaning._raw 时 → 错误事件"""
    state = make_state(stage="analyzing", stage_state=StageState.RUNNING, stages={})

    class FakeAnalyzerAgent:
        async def execute(self, input):
            raise AssertionError("AnalyzerAgent should NOT be called")

    monkeypatch.setattr("app.services.workflow.AnalyzerAgent", FakeAnalyzerAgent)

    events = []
    async for sse in workflow_service.run_stage_only_stream(state, "analyzing"):
        import json
        lines = sse.strip().split("\n")
        evt_name = None
        for line in lines:
            if line.startswith("event: "):
                evt_name = line[7:].strip()
        events.append((evt_name, None))

    event_names = [e[0] for e in events]
    assert "stage_error" in event_names


@pytest.mark.asyncio
async def test_run_stage_only_stream_reporting_requires_analyzing_raw(monkeypatch, patch_persist):
    """reporting 阶段没有 analyzing._raw 时 → 错误事件"""
    state = make_state(stage="reporting", stage_state=StageState.RUNNING, stages={})

    class FakeReporterAgent:
        async def execute(self, input):
            raise AssertionError("ReporterAgent should NOT be called")

    monkeypatch.setattr("app.services.workflow.ReporterAgent", FakeReporterAgent)

    events = []
    async for sse in workflow_service.run_stage_only_stream(state, "reporting"):
        import json
        lines = sse.strip().split("\n")
        evt_name = None
        for line in lines:
            if line.startswith("event: "):
                evt_name = line[7:].strip()
        events.append((evt_name, None))

    event_names = [e[0] for e in events]
    assert "stage_error" in event_names


# ========== 完整 dispatch 模拟 ==========

@pytest.mark.asyncio
async def test_full_dispatch_cleaning_with_mocked_cleaner(monkeypatch, patch_persist):
    """模拟完整 cleaning dispatch：给定 collecting._raw 后应跑 CleanerAgent 并写 stage_output"""
    from datetime import datetime, timezone
    from app.schemas.agent import CollectedItem, CleanedItem

    # 准备 collecting._raw
    raw_item = CollectedItem(
        task_id="t1", source_type="news", source_uri="http://x", title="t",
        content="some content here",
    )
    state = make_state(
        stage="cleaning",
        stage_state=StageState.RUNNING,
        stages={"collecting": {"_raw": {"items": [raw_item.model_dump()]}}},
    )

    # Mock CleanerAgent
    fake_cleaned = CleanedItem(
        task_id="t1", source_type="news", source_uri="http://x", title="t",
        summary="summary", content_chunks=["chunk1"], metadata={},
    )

    class FakeCleanerOutput:
        success = True
        cleaned_items = [fake_cleaned]
        total_removed = 0

    class FakeCleanerAgent:
        async def execute(self, input):
            return FakeCleanerOutput()

    monkeypatch.setattr("app.services.workflow.CleanerAgent", FakeCleanerAgent)

    events = []
    async for sse in workflow_service.run_stage_only_stream(state, "cleaning"):
        import json
        lines = sse.strip().split("\n")
        evt_name = None
        evt_data = None
        for line in lines:
            if line.startswith("event: "):
                evt_name = line[7:].strip()
            elif line.startswith("data: "):
                evt_data = json.loads(line[6:])
        events.append((evt_name, evt_data))

    last_data = events[-1][1]
    assert last_data["stage"] == "cleaning"
    assert last_data["stage_output"]["stage"] == "cleaning"
    assert "cleaned_items" in last_data["stage_output"]
    assert last_data["stage_output"]["stats"]["total_in"] == 1
    assert last_data["stage_output"]["stats"]["total_out"] == 1
    # state 应被更新
    assert state.stage_state == StageState.AWAITING_CONFIRMATION
    assert "cleaning" in state.stages
    assert "_raw" in state.stages["cleaning"]


# ========== Error path ==========

@pytest.mark.asyncio
async def test_run_stage_only_stream_handles_agent_failure(monkeypatch, patch_persist):
    """agent 抛异常时 → stage_state=failed + stage_error SSE 事件"""

    state = make_state(stage="collecting", stage_state=StageState.RUNNING)

    class FakeCollectorAgent:
        async def execute(self, input):
            from app.schemas.agent import CollectorOutput
            return CollectorOutput(success=False, items=[], error="mock failure", warning="")

    monkeypatch.setattr("app.services.workflow.CollectorAgent", FakeCollectorAgent)

    events = []
    async for sse in workflow_service.run_stage_only_stream(state, "collecting"):
        import json
        lines = sse.strip().split("\n")
        evt_name = None
        evt_data = None
        for line in lines:
            if line.startswith("event: "):
                evt_name = line[7:].strip()
            elif line.startswith("data: "):
                evt_data = json.loads(line[6:])
        events.append((evt_name, evt_data))

    event_names = [e[0] for e in events]
    assert "stage_start" in event_names
    assert "stage_error" in event_names
    assert state.stage_state == StageState.FAILED
    assert state.status == "failed"
