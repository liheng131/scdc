import json
import logging
import httpx
from typing import List

from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.core.config import settings
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)


class KeywordExpander:
    def __init__(self):
        self.llm_provider = rumtime_config.get("llm_provider") or "ollama"
        self.default_model = rumtime_config.get("default_model") or settings.default_model
        self.llm_base_url = rumtime_config.get("llm_base_url") or settings.ollama_base_url
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

    def _clean_json_response(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _build_expansion_prompt(self, topic: str) -> str:
        template = """你是一个搜索关键词扩展专家。请将用户的主题扩展为 5-8 个搜索关键词。

要求：
1. 每个关键词必须与用户的问题密切相关
2. 关键词应该覆盖主题的不同方面/角度
3. 关键词之间不要是同义词或高度相关的（例如 "AI" 和 "大模型" 太相似，只选一个）
4. 返回一个 JSON 数组，包含 5-8 个关键词字符串

示例：
用户问题："OpenAI的AI发展态势如何？"
返回：["AI", "算力", "Agent", "Google", "ChatGPT"]

用户问题："{topic}"

请只返回 JSON 数组，不要包含任何其他内容："""
        return template.format(topic=topic)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(2),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, json.JSONDecodeError)),
        reraise=True
    )
    async def _call_llm(self, prompt: str, timeout: int = 10) -> List[str]:
        if self.llm_provider == "gpustack":
            payload = {
                "model": self.default_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 256,
            }
        else:
            payload = {
                "model": self.default_model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.3}
            }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self.llm_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

            if self.llm_provider == "gpustack":
                response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                response_text = data.get("response", "")

            response_text = self._clean_json_response(response_text)
            if not response_text:
                raise json.JSONDecodeError("Empty response after cleaning", "", 0)

            keywords = json.loads(response_text)

            # 验证返回的是列表
            if not isinstance(keywords, list):
                raise ValueError(f"Expected list, got {type(keywords).__name__}")

            # 过滤并确保都是字符串
            keywords = [str(k).strip() for k in keywords if k]

            # 验证数量在 5-8 之间
            if len(keywords) < 1:
                raise ValueError("No keywords returned")

            return keywords

    async def expand_keywords(self, topic: str) -> List[str]:
        """将主题扩展为 5-8 个搜索关键词。

        Args:
            topic: 用户主题

        Returns:
            关键词列表。如果 LLM 调用失败，返回 [topic] 作为降级方案。
        """
        await self._ensure_db_config()
        logger.info(f"KeywordExpander expanding topic: '{topic[:100]}...'")

        try:
            prompt = self._build_expansion_prompt(topic)
            keywords = await self._call_llm(prompt, timeout=10)

            # 限制最多 8 个关键词
            keywords = keywords[:8]

            logger.info(f"Keyword expansion result: {keywords}")
            return keywords

        except httpx.ReadTimeout:
            logger.warning("Keyword expansion timeout, falling back to original topic")
            return [topic]

        except httpx.ConnectError:
            logger.warning("Keyword expansion connection error, falling back to original topic")
            return [topic]

        except json.JSONDecodeError as e:
            logger.warning(f"Keyword expansion JSON parse error ({e}), falling back to original topic")
            return [topic]

        except Exception as e:
            logger.warning(f"Keyword expansion failed ({type(e).__name__}), falling back to original topic")
            return [topic]


# 模块级单例实例
keyword_expander = KeywordExpander()
