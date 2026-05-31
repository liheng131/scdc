import logging
import httpx
from typing import List
from app.core.runtime_config import rumtime_config

logger = logging.getLogger(__name__)


class RerankService:
    def __init__(self):
        self.base_url = ""
        self.model = ""
        self.provider = ""
        self.api_key = ""
        self._db_config_loaded = False

    async def _ensure_db_config(self):
        if self._db_config_loaded:
            return
        self._db_config_loaded = True
        try:
            db_config = await rumtime_config.get_default_model_config("rerank")
            if db_config:
                self.base_url = db_config["base_url"].rstrip('/') if db_config.get("base_url") else ""
                self.model = db_config.get("model_name") or self.model
                self.provider = db_config["provider"].lower() if db_config.get("provider") else ""
                if db_config.get("api_key"):
                    self.api_key = db_config["api_key"]
        except Exception:
            pass

    async def rerank(self, query: str, documents: List[str]) -> List[dict]:
        """
        对文档列表按与查询的相关性重排序。
        返回按相关性降序排列的结果列表，每项包含：
          {
              "index": int,     # 原始 documents 中的索引
              "text": str,      # 文档原文
              "score": float    # 相关性分数
          }
        """
        await self._ensure_db_config()
        if not self.base_url or not self.model:
            logger.warning("Rerank service not configured, skipping rerank.")
            return []

        if not documents:
            return []

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                url = f"{self.base_url}/v1/rerank"
                payload = {
                    "model": self.model,
                    "query": query,
                    "documents": documents,
                }
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                reranked = []
                for r in results:
                    idx = r.get("index", 0)
                    reranked.append({
                        "index": idx,
                        "text": documents[idx] if 0 <= idx < len(documents) else "",
                        "score": r.get("relevance_score", r.get("score", 0.0)),
                    })
                return reranked
        except httpx.HTTPStatusError as e:
            logger.error(f"Rerank HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Rerank request error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Rerank unexpected error: {str(e)}")
            raise
