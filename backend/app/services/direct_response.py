import json
import logging
import traceback
from typing import AsyncGenerator, Optional

import httpx

from app.core.config import settings
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的智能助手，隶属于SCDC智能市场洞察分析系统。

关于你的能力：
- 你可以帮助用户进行行业研究、竞争分析、市场趋势分析等深度市场洞察工作
- 当用户需要市场分析时，你可以协调系统内的搜索引擎、AI分析引擎和报告生成器来完成完整的市场洞察报告
- 你也可以回答一般性问题，进行日常对话

请用中文回答用户的问题。回答要简洁、准确、有帮助。"""


class DirectResponseService:
    def __init__(self):
        self.llm_provider = rumtime_config.get("llm_provider")
        self.default_model = rumtime_config.get("default_model")
        self.llm_base_url = rumtime_config.get("llm_base_url")
        self.llm_api_key = settings.llm_api_key
        self._db_config_loaded = False

        self._build_llm_config()

    def _build_llm_config(self):
        if self.llm_provider == "gpustack":
            self.llm_url = f"{self.llm_base_url.rstrip('/')}/v1/chat/completions"
            self.headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.llm_url = f"{self.llm_base_url.rstrip('/')}/api/generate"
            self.headers = {}

    async def _ensure_db_config(self):
        if self._db_config_loaded:
            return
        self._db_config_loaded = True
        try:
            db_config = await rumtime_config.get_default_model_config("llm")
            if db_config:
                self.llm_provider = db_config["provider"].lower() if db_config["provider"] else self.llm_provider
                self.default_model = db_config["model_name"] or self.default_model
                if db_config["base_url"]:
                    self.llm_base_url = db_config["base_url"]
                if db_config["api_key"]:
                    self.llm_api_key = db_config["api_key"]
                self._build_llm_config()
        except Exception:
            pass

    def _sse(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    def _get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def _retrieve_rag_context(self, query: str) -> str:
        """检索向量库获取相关历史报告片段。

        Returns: 格式化的上下文字符串，失败时返回空字符串。
        """
        if not query:
            return ""
        try:
            from app.services.vectorstore import VectorStoreService
            from app.services.rerank import RerankService
            from app.services.embedding import EmbeddingService

            emb_service = EmbeddingService()
            embeddings = await emb_service.embed_texts_or_empty([query])
            if not embeddings or not embeddings[0]:
                logger.info("RAG: embedding returned empty, skipping")
                return ""

            vs_service = VectorStoreService()
            if not vs_service._connected:
                logger.info("RAG: Milvus not connected, skipping")
                return ""
            if not vs_service.collection_exists():
                logger.info("RAG: collection does not exist, skipping")
                return ""
            hits = vs_service.search(embeddings[0], top_k=20)
            if not hits:
                logger.info("RAG: no vector hits for query")
                return ""

            documents = [hit.get("text", "") for hit in hits]
            rerank_service = RerankService()
            reranked = await rerank_service.rerank(query, documents)
            top_indices = [r["index"] for r in reranked[:3] if r.get("index") is not None]
            context_snippets = [documents[i] for i in top_indices if 0 <= i < len(documents)]

            if not context_snippets:
                return ""

            context_text = "\n\n---\n\n".join(context_snippets)
            logger.info(
                "RAG: retrieved %d hits, reranked to %d context snippets",
                len(hits), len(context_snippets),
            )
            return context_text
        except Exception as e:
            logger.warning("RAG retrieval failed: %s, falling back to no-RAG mode", e)
            return ""

    async def generate_response_stream(
        self,
        message: str,
        conversation_history: list = None,
        workflow_id: str = None,
        use_rag: bool = False,
    ) -> AsyncGenerator[str, None]:
        await self._ensure_db_config()
        logger.info(
            f"DirectResponseService generating response for: '{message[:100]}...' (use_rag={use_rag})"
        )

        if not self.llm_base_url:
            logger.warning("LLM base URL not configured for direct response")
            yield self._sse("error", {"error": "LLM服务未配置，请先配置AI模型"})
            return

        system_prompt = self._get_system_prompt()
        if use_rag:
            rag_context = await self._retrieve_rag_context(message)
            if rag_context:
                system_prompt = (
                    f"{system_prompt}\n\n"
                    f"以下是从历史报告中检索到的相关内容片段（仅供参考）：\n\n{rag_context}\n\n"
                    f"如果用户问题与上述片段相关，请引用；否则按自己的知识回答。"
                )

        try:
            if self.llm_provider == "gpustack":
                async for chunk in self._stream_gpustack(
                    message, conversation_history, workflow_id, system_prompt=system_prompt
                ):
                    yield chunk
            else:
                async for chunk in self._stream_ollama(
                    message, conversation_history, workflow_id, system_prompt=system_prompt
                ):
                    yield chunk
        except httpx.ConnectError as e:
            logger.error(f"DirectResponseService LLM connect failed: {e}")
            yield self._sse("error", {"error": "AI模型服务连接失败，请检查LLM服务是否正常运行"})
        except httpx.ReadTimeout as e:
            logger.error(f"DirectResponseService LLM read timeout: {e}")
            yield self._sse("error", {"error": "AI模型响应超时，请稍后再试"})
        except Exception as e:
            logger.error(f"DirectResponseService streaming failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            yield self._sse("error", {"error": f"生成回复时出错: {str(e)[:500]}"})

    async def _stream_gpustack(
        self,
        message: str,
        conversation_history: list = None,
        workflow_id: str = None,
        system_prompt: str = None,
    ) -> AsyncGenerator[str, None]:
        effective_system_prompt = system_prompt if system_prompt else SYSTEM_PROMPT
        messages = [{"role": "system", "content": effective_system_prompt}]

        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    # 截断过长的历史消息内容，避免超出 LLM token 限制
                    if len(content) > 2000:
                        content = content[:2000] + "...(内容已截断)"
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        payload = {
            "model": self.default_model,
            "messages": messages,
            "temperature": rumtime_config.get("temperature", 0.5),
            "max_tokens": rumtime_config.get("max_tokens", 4096),
            "stream": True,
        }

        buffer = ""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", self.llm_url, json=payload, headers=self.headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices")
                        if not choices:
                            continue
                        content = choices[0].get("delta", {}).get("content", "")
                        if content:
                            buffer += content
                            if len(buffer) >= 20:
                                yield self._sse("direct_response", {"content": buffer})
                                buffer = ""
                    except json.JSONDecodeError:
                        continue

        if buffer:
            yield self._sse("direct_response", {"content": buffer})

        yield self._sse("direct_response_done", {"workflow_id": workflow_id})

    async def _stream_ollama(
        self,
        message: str,
        conversation_history: list = None,
        workflow_id: str = None,
        system_prompt: str = None,
    ) -> AsyncGenerator[str, None]:
        effective_system_prompt = system_prompt if system_prompt else SYSTEM_PROMPT
        prompt_parts = [effective_system_prompt, ""]
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    prompt_parts.append(f"用户: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"助手: {content}")
        prompt_parts.append(f"用户: {message}")
        prompt_parts.append("助手: ")
        prompt = "\n".join(prompt_parts)

        payload = {
            "model": self.default_model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": rumtime_config.get("temperature", 0.5)},
        }

        buffer = ""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", self.llm_url, json=payload, headers=self.headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("response", "")
                        if content:
                            buffer += content
                            if len(buffer) >= 20:
                                yield self._sse("direct_response", {"content": buffer})
                                buffer = ""
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

        if buffer:
            yield self._sse("direct_response", {"content": buffer})

        yield self._sse("direct_response_done", {"workflow_id": workflow_id})