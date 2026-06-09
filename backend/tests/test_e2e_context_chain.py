"""
端到端测试 —— 同会话多轮 context 链路验证

对应 spec: .trae/specs/enhance-intent-routing-and-rag-coverage/ (Task 5)

覆盖链路：
1. 前端 conversationHistory 构造（含 user + assistant 角色）        → 测试 4 静态检查
2. 后端 WorkflowService.run_follow_up_stream() 透传 history         → 测试 3
3. DirectResponseService.generate_response_stream() 构造 LLM messages → 测试 1
4. use_rag=True 时 RAG 片段注入 system prompt                       → 测试 2

所有 httpx 调用均通过 AsyncMock / 自定义 FakeClient 拦截，不打真实 LLM 服务。
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# 确保 backend/ 目录在 sys.path 中（与 test_health.py 保持一致）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ============================================================================
# Mock 工具：拦截 httpx.AsyncClient.stream 以捕获 LLM payload
# ============================================================================

class _FakeStreamResp:
    """伪装 httpx 的流式响应对象。"""

    def __init__(self, lines: List[str]):
        self._lines = lines

    def raise_for_status(self) -> None:
        """模拟无错误的响应。"""
        return None

    async def aiter_lines(self):
        """异步按行迭代伪造的 SSE 行。"""
        for line in self._lines:
            yield line


class _FakeStreamCM:
    """`client.stream(...)` 返回的异步上下文管理器。"""

    def __init__(self, resp: _FakeStreamResp):
        self._resp = resp

    async def __aenter__(self) -> _FakeStreamResp:
        return self._resp

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeAsyncClient:
    """伪装 httpx.AsyncClient —— `async with httpx.AsyncClient(...) as client`。

    - `stream(method, url, json=..., headers=...)` 捕获 `json` 作为 payload
    - 可通过 `set_sse_lines(...)` 注入伪造的 SSE 行
    - 通过 `captured_payload` 读取最近一次 stream 调用时的 json 字段
    """

    def __init__(self, *args, **kwargs):
        self._sse_lines: List[str] = []
        self.captured_method: str = ""
        self.captured_url: str = ""
        self.captured_headers: Dict[str, str] = {}
        self.captured_payload: Dict[str, Any] = {}

    def set_sse_lines(self, lines: List[str]) -> None:
        self._sse_lines = lines

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def stream(self, method: str, url: str, json: Any = None, headers: Dict[str, str] = None, **kwargs):
        self.captured_method = method
        self.captured_url = url
        self.captured_headers = headers or {}
        self.captured_payload = json or {}
        return _FakeStreamCM(_FakeStreamResp(self._sse_lines))


def _install_fake_http_client(monkeypatch, fake: _FakeAsyncClient) -> None:
    """把 `app.services.direct_response.httpx.AsyncClient` 替换为 fake 工厂。"""
    import app.services.direct_response as dr_module
    import httpx

    monkeypatch.setattr(dr_module.httpx, "AsyncClient", lambda *a, **kw: fake)


# ============================================================================
# 测试 1: conversation_history 透传到 LLM request
# ============================================================================

@pytest.mark.asyncio
async def test_e2e_context_chain_history_passes_to_llm_payload(monkeypatch):
    """
    验证：DirectResponseService.generate_response_stream() 收到 conversation_history 后，
    实际发出的 LLM request payload['messages'] 数组应按
    [system, ...history(保留 user/assistant 顺序), user(当前消息)] 顺序拼接。
    """
    from app.services.direct_response import DirectResponseService

    fake_client = _FakeAsyncClient()
    # 伪造一条足够长的 token，使 buffer>=20 触发一次 yield；
    # 最后再追加 data: [DONE] 让循环结束
    fake_client.set_sse_lines([
        'data: {"choices":[{"delta":{"content":"这是基于历史的回答。"}}]}',
        'data: [DONE]',
    ])
    _install_fake_http_client(monkeypatch, fake_client)

    # 强制走 gpustack provider（OpenAI 风格 messages 数组）
    monkeypatch.setattr(
        "app.services.direct_response.rumtime_config.get",
        lambda key, default=None: {
            "llm_provider": "gpustack",
            "default_model": "test-model",
            "llm_base_url": "http://fake-llm/v1",
            "temperature": 0.5,
            "max_tokens": 1024,
        }.get(key, default),
    )

    svc = DirectResponseService()
    svc.llm_provider = "gpustack"
    svc.default_model = "test-model"
    svc.llm_base_url = "http://fake-llm"
    svc._db_config_loaded = True
    svc._build_llm_config()

    history: List[Dict[str, str]] = [
        {"role": "user", "content": "AI 芯片市场分析"},
        {"role": "assistant", "content": "这是 2025 年市场报告..."},
    ]

    # 消费整个异步生成器
    chunks: List[str] = []
    async for chunk in svc.generate_response_stream(
        "刚才提到的市场规模具体数据",
        conversation_history=history,
        workflow_id=None,
        use_rag=False,
    ):
        chunks.append(chunk)

    # 验证捕获到的 payload
    assert fake_client.captured_method == "POST"
    assert "chat/completions" in fake_client.captured_url

    payload = fake_client.captured_payload
    assert "messages" in payload, f"payload missing 'messages': {payload}"

    messages = payload["messages"]

    # 断言 1: 第一条必须是 system
    assert messages[0]["role"] == "system", f"messages[0] should be system, got {messages[0]}"
    assert isinstance(messages[0]["content"], str) and len(messages[0]["content"]) > 0

    # 断言 2: history 中 user 消息紧随 system
    assert messages[1] == {"role": "user", "content": "AI 芯片市场分析"}, (
        f"messages[1] expected user history, got {messages[1]}"
    )

    # 断言 3: history 中 assistant 消息紧随其后
    assert messages[2] == {"role": "assistant", "content": "这是 2025 年市场报告..."}, (
        f"messages[2] expected assistant history, got {messages[2]}"
    )

    # 断言 4: 最后一条必须是当前 user 消息
    assert messages[-1] == {"role": "user", "content": "刚才提到的市场规模具体数据"}, (
        f"messages[-1] expected current user message, got {messages[-1]}"
    )

    # 断言 5: 总长度 = 1 (system) + len(history) + 1 (current user) = 4
    assert len(messages) == 4, f"expected 4 messages, got {len(messages)}: {messages}"


# ============================================================================
# 测试 2: use_rag=True 时 system prompt 含 RAG 片段占位
# ============================================================================

@pytest.mark.asyncio
async def test_e2e_context_chain_use_rag_injects_context_into_system(monkeypatch):
    """
    验证：use_rag=True 时，DirectResponseService 会先调 VectorStore / Rerank / Embedding，
    并把检索到的 RAG 片段拼接到 system prompt 里。
    """
    from app.services import direct_response as dr_module
    from app.services.direct_response import DirectResponseService

    # ---- 伪造 VectorStoreService: search 返回 3 个 hit ----
    class FakeVectorStore:
        _connected = True

        def __init__(self, *args, **kwargs):
            pass

        def collection_exists(self) -> bool:
            return True

        def search(self, query_vector, top_k: int = 20, filter_expr=None) -> List[Dict[str, Any]]:
            return [
                {"id": 1, "text": "AI 芯片 2025 年市场规模约 1000 亿美元", "score": 0.95},
                {"id": 2, "text": "英伟达 GPU 占据 80% 市场份额", "score": 0.90},
                {"id": 3, "text": "国产芯片厂商海思增速显著", "score": 0.85},
            ]

    # ---- 伪造 RerankService: rerank 返回 top 3 ----
    class FakeRerank:
        def __init__(self, *args, **kwargs):
            pass

        async def rerank(self, query: str, documents: List[str]) -> List[Dict[str, Any]]:
            return [
                {"index": 0, "text": documents[0], "score": 0.99},
                {"index": 1, "text": documents[1], "score": 0.88},
                {"index": 2, "text": documents[2], "score": 0.77},
            ]

    # ---- 伪造 EmbeddingService: 返回固定 768 维向量 ----
    class FakeEmbedding:
        def __init__(self, *args, **kwargs):
            pass

        async def embed_texts_or_empty(self, texts: List[str]) -> List[List[float]]:
            return [[0.1] * 768]

    # 替换 vectorstore / rerank / embedding 模块中的类
    # direct_response 在函数内部使用 `from app.services.vectorstore import VectorStoreService`
    # 因此 patch 模块级 symbol 即可被新导入读到
    import app.services.vectorstore as vs_module
    import app.services.rerank as rr_module
    import app.services.embedding as em_module

    monkeypatch.setattr(vs_module, "VectorStoreService", FakeVectorStore)
    monkeypatch.setattr(rr_module, "RerankService", FakeRerank)
    monkeypatch.setattr(em_module, "EmbeddingService", FakeEmbedding)

    # ---- 拦截 httpx ----
    fake_client = _FakeAsyncClient()
    fake_client.set_sse_lines([
        'data: {"choices":[{"delta":{"content":"基于历史报告的 RAG 增强回答。"}}]}',
        'data: [DONE]',
    ])
    _install_fake_http_client(monkeypatch, fake_client)

    # ---- 构造 DirectResponseService 并强制走 gpustack ----
    monkeypatch.setattr(
        dr_module.rumtime_config,
        "get",
        lambda key, default=None: {
            "llm_provider": "gpustack",
            "default_model": "test-model",
            "llm_base_url": "http://fake-llm",
            "temperature": 0.5,
            "max_tokens": 1024,
        }.get(key, default),
    )

    svc = DirectResponseService()
    svc.llm_provider = "gpustack"
    svc.default_model = "test-model"
    svc.llm_base_url = "http://fake-llm"
    svc._db_config_loaded = True
    svc._build_llm_config()

    chunks: List[str] = []
    async for chunk in svc.generate_response_stream(
        "AI 芯片市场规模",
        conversation_history=None,
        workflow_id=None,
        use_rag=True,
    ):
        chunks.append(chunk)

    payload = fake_client.captured_payload
    messages = payload["messages"]
    system_content = messages[0]["content"]

    # 断言 1: system prompt 含原始系统角色描述
    assert "智能助手" in system_content or "智能市场洞察" in system_content, (
        f"system prompt missing base role description: {system_content[:200]}"
    )

    # 断言 2: system prompt 含 RAG context 标识
    assert "以下是从历史报告中检索到的相关内容片段" in system_content, (
        f"system prompt missing RAG context placeholder, got: {system_content[:500]}"
    )

    # 断言 3: system prompt 拼接了至少一个检索片段
    rag_keywords = ["AI 芯片 2025", "英伟达 GPU", "海思"]
    found_keywords = [kw for kw in rag_keywords if kw in system_content]
    assert len(found_keywords) >= 1, (
        f"expected at least one RAG keyword in system prompt, "
        f"got none. system content head: {system_content[:800]}"
    )

    # 断言 4: 只有 system + 当前 user（没传 history），不应有重复 user
    assert len(messages) == 2, f"expected 2 messages (system + current user), got {len(messages)}"
    assert messages[1] == {"role": "user", "content": "AI 芯片市场规模"}


# ============================================================================
# 测试 3: WorkflowService.run_follow_up_stream 透传 history
# ============================================================================

@pytest.mark.asyncio
async def test_e2e_context_chain_workflow_run_follow_up_passes_history(monkeypatch):
    """
    验证：WorkflowService.run_follow_up_stream() 收到的 conversation_history
    会原封不动透传给底层的 DirectResponseService.generate_response_stream()。
    """
    from app.services.workflow import WorkflowService, WorkflowState

    svc = WorkflowService()

    # 准备一个 mock workflow state
    workflow_id = "wf-mock-001"
    svc._workflows[workflow_id] = WorkflowState(
        workflow_id=workflow_id,
        topic="AI 芯片市场",
        max_items=0,
        dimensions=[],
        conversation_history=[],
        use_rag=False,
    )

    # 拦截 DirectResponseService.generate_response_stream
    captured: Dict[str, Any] = {}

    async def fake_gen(message, conversation_history=None, workflow_id=None, use_rag=False):
        captured["message"] = message
        captured["conversation_history"] = conversation_history
        captured["workflow_id"] = workflow_id
        captured["use_rag"] = use_rag
        # 必须至少含一个 yield 才算合法 async generator
        yield "event: direct_response_done\ndata: {}\n\n"

    # 替换 _direct_response.generate_response_stream
    monkeypatch.setattr(
        svc._direct_response,
        "generate_response_stream",
        fake_gen,
    )

    history: List[Dict[str, str]] = [{"role": "user", "content": "原始问题"}]

    chunks: List[str] = []
    async for chunk in svc.run_follow_up_stream(
        workflow_id=workflow_id,
        message="追问",
        conversation_history=history,
        use_rag=False,
    ):
        chunks.append(chunk)

    # 断言：generate_response_stream 收到的 history 与传入的一致
    assert captured["conversation_history"] == history, (
        f"expected history {history}, got {captured['conversation_history']}"
    )
    assert captured["message"] == "追问"
    assert captured["use_rag"] is False


@pytest.mark.asyncio
async def test_e2e_context_chain_workflow_follow_up_falls_back_to_state_history(monkeypatch):
    """
    验证：调用 run_follow_up_stream() 时若 conversation_history=None，
    应回退使用 WorkflowState.conversation_history。
    """
    from app.services.workflow import WorkflowService, WorkflowState

    svc = WorkflowService()
    workflow_id = "wf-mock-002"
    state_history = [
        {"role": "user", "content": "state 中的原始问题"},
        {"role": "assistant", "content": "state 中的助手回答"},
    ]
    svc._workflows[workflow_id] = WorkflowState(
        workflow_id=workflow_id,
        topic="AI 芯片",
        max_items=0,
        dimensions=[],
        conversation_history=state_history,
        use_rag=False,
    )

    captured: Dict[str, Any] = {}

    async def fake_gen(message, conversation_history=None, workflow_id=None, use_rag=False):
        captured["conversation_history"] = conversation_history
        yield "event: direct_response_done\ndata: {}\n\n"

    monkeypatch.setattr(svc._direct_response, "generate_response_stream", fake_gen)

    chunks = []
    async for chunk in svc.run_follow_up_stream(
        workflow_id=workflow_id,
        message="追问",
        conversation_history=None,  # 显式传 None
        use_rag=False,
    ):
        chunks.append(chunk)

    assert captured["conversation_history"] == state_history, (
        f"expected state history fallback, got {captured['conversation_history']}"
    )


# ============================================================================
# 测试 4: WorkflowView.vue 静态检查 —— conversationHistory 含 user + assistant
# ============================================================================

def _read_workflow_view_source() -> str:
    """读取 frontend/src/views/WorkflowView.vue 的源文本。"""
    # 当前测试文件位于 backend/tests/，需要回到 repo 根再进 frontend
    # tests/ -> backend/ -> repo root -> frontend/
    tests_dir = Path(__file__).resolve().parent
    backend_dir = tests_dir.parent
    repo_root = backend_dir.parent
    vue_path = repo_root / "frontend" / "src" / "views" / "WorkflowView.vue"
    assert vue_path.exists(), f"WorkflowView.vue not found at {vue_path}"
    return vue_path.read_text(encoding="utf-8")


def test_e2e_context_chain_workflow_view_conversation_history_contains_both_roles():
    """
    静态检查 frontend/src/views/WorkflowView.vue 中 sendMessage() 构造
    conversationHistory 的逻辑是否同时包含 user 和 assistant 角色。

    期望特征：
    1. 存在 'conversationHistory'（或 'conversation_history'）变量
    2. 该变量通过 .map(m => ({ role: m.role, ... })) 复用消息的角色字段
    3. 消息源 activeConv.messages 中同时 push 了 role: 'user' 与 role: 'assistant'
    """
    source = _read_workflow_view_source()

    # 1. 必须有 conversationHistory / conversation_history 字段
    assert "conversationHistory" in source or "conversation_history" in source, (
        "WorkflowView.vue must reference conversationHistory / conversation_history"
    )

    # 2. sendMessage 内的 user 消息 push
    assert "role: 'user'" in source, (
        "WorkflowView.vue must push user role messages into the conversation list"
    )
    # 3. sendMessage 内的 assistant 消息 push
    assert "role: 'assistant'" in source, (
        "WorkflowView.vue must push assistant role messages into the conversation list"
    )

    # 4. conversationHistory 构造处使用了 .map(m => ({ role: m.role, content: ... }))
    #    兼容写法：可能用 .map((m) => ({ role: m.role, ... }))
    assert "role: m.role" in source, (
        "conversationHistory mapping must preserve the original message role "
        "via 'role: m.role' rather than hardcoding it"
    )

    # 5. 在 sendMessage 函数中，"追问模式"分支应包含以上要素
    send_message_idx = source.find("const sendMessage =")
    assert send_message_idx > -1, "sendMessage function not found in WorkflowView.vue"
    send_message_body = source[send_message_idx:]

    assert "role: 'user'" in send_message_body, (
        "sendMessage must push role:'user' messages"
    )
    assert "role: 'assistant'" in send_message_body, (
        "sendMessage must push role:'assistant' messages"
    )
    assert "conversationHistory" in send_message_body or "conversation_history" in send_message_body, (
        "sendMessage must construct a conversationHistory / conversation_history payload"
    )


# ============================================================================
# 单元辅助：避免 main 模块副作用（main 启动时 lifespan 会建表、scheduler 等）
# 本测试文件不 import app.main，因此不会触发那些副作用。
# ============================================================================
