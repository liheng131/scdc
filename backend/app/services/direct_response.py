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
- 你具备多模态能力：当用户上传图片时，请**直接观察图片内容**并回答用户关于图片的问题（如"附图是什么内容"、"图片中显示什么数据"等）
  - 仔细阅读图中的文字、图表、表格、流程图、公式等所有视觉元素
  - 描述图片的具体内容、关键信息、可识别的图表类型与数据趋势
  - 回答时明确指出"从图片中可以看到..."或"图片内容是..."以表明你确实识别了图片

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

    async def _load_attachments(self, attachment_ids: list) -> tuple[list, list]:
        """根据 attachment_ids 从 DB 加载附件元数据。
        返回 (image_attachments, text_attachments)：
        - image_attachments: List[dict{filename, mime, base64}]，多模态 LLM 自行识别格式
        - text_attachments: List[dict{filename, content}]，作为文本上下文拼入 system prompt
        """
        if not attachment_ids:
            return [], []
        try:
            from app.core.db import async_session_factory
            from app.models.attachment import Attachment
            from sqlalchemy import select
            from app.services.minio_client import minio_client
            import base64
        except Exception as e:
            logger.warning("_load_attachments: 依赖导入失败: %s", e)
            return [], []

        # 文件扩展名 → MIME 类型映射（用于 OpenAI 兼容的 image_url.data URL）
        import mimetypes
        _EXT_MIME = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }

        image_attachments: list = []
        text_attachments: list = []

        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Attachment).where(Attachment.id.in_(attachment_ids))
                )
                attachments = result.scalars().all()
        except Exception as e:
            logger.warning("_load_attachments: DB 查询失败: %s", e)
            return [], []

        for att in attachments:
            try:
                if att.file_type == "image":
                    obj = minio_client.get_object(att.minio_object_key)
                    if obj is None:
                        logger.warning("image attachment %s 字节流为空,跳过", att.id)
                        continue
                    img_b64 = base64.b64encode(obj).decode("ascii")
                    # 从文件名推断 MIME（不能硬编码 jpeg,PNG/BMP/WebP 都会失败）
                    ext = ("." + (att.filename or "").rsplit(".", 1)[-1]).lower() if "." in (att.filename or "") else ""
                    mime = _EXT_MIME.get(ext) or mimetypes.guess_type(att.filename or "")[0] or "image/jpeg"
                    # metadata["format"] 字段是 PIL 解析时记录的（小写 "png"/"jpeg"），优先使用
                    fmt_meta = (att.extra_metadata or {}).get("format", "").lower() if att.extra_metadata else ""
                    if fmt_meta in ("png", "gif", "bmp", "tiff", "webp"):
                        mime = f"image/{fmt_meta}"
                    elif fmt_meta == "jpeg":
                        mime = "image/jpeg"
                    image_attachments.append({
                        "filename": att.filename,
                        "mime": mime,
                        "base64": img_b64,
                    })
                    logger.info(
                        "Loaded image attachment %s (%d bytes, mime=%s)",
                        att.filename, len(obj), mime,
                    )
                else:
                    if att.parsed_content:
                        text_attachments.append({
                            "filename": att.filename,
                            "content": att.parsed_content,
                        })
            except Exception as e:
                logger.warning("Failed to load attachment %s: %s", att.filename, e)
                continue

        return image_attachments, text_attachments

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
        attachment_ids: list = None,
        workflow_state: object = None,
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

        # 加载用户附件：图片转为 base64 给多模态模型；非图片以文本形式作为上下文
        image_attachments, text_attachments = await self._load_attachments(attachment_ids or [])

        if text_attachments:
            att_text = "\n\n---\n\n".join(
                f"[附件: {a['filename']}]\n{a['content']}" for a in text_attachments
            )
            system_prompt = (
                f"{system_prompt}\n\n"
                f"用户上传了以下附件，请将其作为参考材料回答问题：\n\n{att_text}\n"
            )

        if image_attachments:
            logger.info(
                "Multimodal: passing %d image attachment(s) to %s",
                len(image_attachments), self.default_model,
            )

        try:
            if self.llm_provider == "gpustack":
                async for chunk in self._stream_gpustack(
                    message, conversation_history, workflow_id,
                    system_prompt=system_prompt, image_attachments=image_attachments,
                    workflow_state=workflow_state,
                ):
                    yield chunk
            else:
                async for chunk in self._stream_ollama(
                    message, conversation_history, workflow_id,
                    system_prompt=system_prompt, image_attachments=image_attachments,
                    workflow_state=workflow_state,
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
        image_attachments: list = None,
        workflow_state: object = None,
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

        # 当前消息:有图片时用 OpenAI 多模态 content 数组格式
        # 每个 image_attachment 携带自己的 mime 字段,data URL 必须使用真实格式
        if image_attachments:
            content_blocks: list = [{"type": "text", "text": message}]
            for img in image_attachments:
                mime = img.get("mime") or "image/jpeg"
                b64 = img.get("base64") if isinstance(img, dict) else img
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            messages.append({"role": "user", "content": content_blocks})
        else:
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
                    # Check cancellation at each chunk
                    if workflow_state is not None and getattr(workflow_state, "cancelled", False):
                        logger.info(f"[{workflow_id}] LLM stream cancelled by user (gpustack)")
                        resp.aclose()
                        return
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
        image_attachments: list = None,
        workflow_state: object = None,
    ) -> AsyncGenerator[str, None]:
        """调用 Ollama 推理。
        - 有图片附件时使用 /api/chat 多模态端点(images: base64)
        - 无图片时回退到 /api/generate 文本端点
        """
        effective_system_prompt = system_prompt if system_prompt else SYSTEM_PROMPT

        # 构造 messages 列表
        messages = [{"role": "system", "content": effective_system_prompt}]
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    if len(content) > 2000:
                        content = content[:2000] + "...(内容已截断)"
                    messages.append({"role": role, "content": content})

        # 当前用户消息:有图片时 content 为 list(文本+图像块),无图时为纯文本
        # 兼容两种 image_attachments 格式:新格式 list[dict{mime,base64}],旧格式 list[base64 str]
        if image_attachments:
            images_b64: list = []
            for img in image_attachments:
                if isinstance(img, dict):
                    images_b64.append(img.get("base64") or "")
                else:
                    images_b64.append(img)
            user_msg: dict = {
                "role": "user",
                "content": message,
                "images": images_b64,  # Ollama 字段:List[base64 str]
            }
        else:
            user_msg = {"role": "user", "content": message}
        messages.append(user_msg)

        # 有图走 /api/chat 多模态端点;无图走 /api/generate(更轻量)
        if image_attachments:
            chat_url = f"{self.llm_base_url.rstrip('/')}/api/chat"
            payload = {
                "model": self.default_model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": rumtime_config.get("temperature", 0.5)},
            }
            response_field = "message"
        else:
            chat_url = f"{self.llm_base_url.rstrip('/')}/api/generate"
            # /api/generate 用扁平 prompt,把 messages 拼成字符串
            prompt_parts = [effective_system_prompt, ""]
            for m in messages[1:]:
                if m["role"] == "user":
                    prompt_parts.append(f"用户: {m['content']}")
                elif m["role"] == "assistant":
                    prompt_parts.append(f"助手: {m['content']}")
            prompt_parts.append("助手: ")
            payload = {
                "model": self.default_model,
                "prompt": "\n".join(prompt_parts),
                "stream": True,
                "options": {"temperature": rumtime_config.get("temperature", 0.5)},
            }
            response_field = "response"

        buffer = ""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", chat_url, json=payload, headers=self.headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    # Check cancellation at each chunk
                    if workflow_state is not None and getattr(workflow_state, "cancelled", False):
                        logger.info(f"[{workflow_id}] LLM stream cancelled by user (ollama)")
                        resp.aclose()
                        return
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = (data.get(response_field) or {}).get("content", "") if response_field == "message" else data.get(response_field, "")
                        # /api/chat 的 message 是 dict{"content": str}; /api/generate 的 response 是 str
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