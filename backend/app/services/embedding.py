import logging
import httpx
from typing import List
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, base_url: str = None, model: str = None, provider: str = None, api_key: str = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip('/')
        self.model = model or settings.embedding_model
        self.provider = (provider or settings.llm_provider).lower()
        self.api_key = api_key or settings.llm_api_key
        self._db_config_loaded = False

    async def _ensure_db_config(self):
        if self._db_config_loaded:
            return
        self._db_config_loaded = True
        try:
            from app.core.runtime_config import rumtime_config
            db_config = await rumtime_config.get_default_model_config("embedding")
            if db_config:
                self.base_url = db_config["base_url"].rstrip('/') if db_config.get("base_url") else self.base_url
                self.model = db_config.get("model_name") or self.model
                self.provider = db_config["provider"].lower() if db_config.get("provider") else self.provider
                if db_config.get("api_key"):
                    self.api_key = db_config["api_key"]
        except Exception:
            pass

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        await self._ensure_db_config()
        if self.provider == "gpustack":
            return await self._embed_gpustack(texts)
        else:
            return await self._embed_ollama(texts)

    async def embed_texts_or_empty(self, texts: List[str]) -> List[List[float]]:
        try:
            return await self.embed_texts(texts)
        except Exception as e:
            logger.warning(f"Embedding failed, returning empty: {e}")
            return []

    async def _embed_ollama(self, texts: List[str]) -> List[List[float]]:
        embeddings: List[List[float]] = []
        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                for text in texts:
                    try:
                        url = f"{self.base_url}/api/embeddings"
                        payload = {"model": self.model, "prompt": text}
                        resp = await client.post(url, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        embedding = data.get("embedding", [])
                        if not embedding:
                            logger.warning(f"Ollama returned empty embedding for text: {text[:50]}...")
                            continue
                        embeddings.append(embedding)
                    except (httpx.HTTPStatusError, httpx.RequestError) as e:
                        logger.warning(f"Ollama embedding unavailable: {str(e)[:200]}")
                        return embeddings if embeddings else []
                    except Exception as e:
                        logger.warning(f"Ollama embedding error for text: {str(e)[:200]}")
                        continue
        except Exception as e:
            logger.warning(f"Ollama embedding service unreachable: {str(e)[:200]}")
        return embeddings

    async def _embed_gpustack(self, texts: List[str]) -> List[List[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                url = f"{self.base_url}/v1/embeddings"
                payload = {"input": texts, "model": self.model}
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                embeddings: List[List[float]] = []
                for item in sorted(items, key=lambda x: x.get("index", 0)):
                    embedding = item.get("embedding", [])
                    embeddings.append(embedding)
                if len(embeddings) != len(texts):
                    raise ValueError(
                        f"GPUStack returned {len(embeddings)} embeddings, expected {len(texts)}"
                    )
                return embeddings
        except httpx.HTTPStatusError as e:
            logger.error(f"GPUStack embedding HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"GPUStack embedding request error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"GPUStack embedding unexpected error: {str(e)}")
            raise