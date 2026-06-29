"""
Pexels 图片搜索客户端

为报告提供高质量商业图片（替代纯网页截图），显著提升视觉质量。

API: https://api.pexels.com/v1
- GET /search?query=keyword&per_page=5&locale=zh-CN
- 每请求返回 15-80 张授权图片
- 速率限制: 200 requests/hour（免费版）

图片嵌入流程:
  Pexels search → URL list → HTTP download → base64 encode → CollectorOutput
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

PEXELS_BASE_URL = "https://api.pexels.com/v1"


class PexelsClient:
    """Pexels 图片搜索客户端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=PEXELS_BASE_URL,
            headers={"Authorization": api_key},
            timeout=15,
        )

    async def search(
        self,
        query: str,
        per_page: int = 5,
        page: int = 1,
        orientation: str = "landscape",
        size: str = "medium",
        locale: str = "zh-CN",
    ) -> List[Dict[str, Any]]:
        """搜索 Pexels 图片

        Args:
            query: 搜索关键词
            per_page: 每页数量 (1-80)
            orientation: landscape / portrait / square
            size: large(24MP) / medium(12MP) / small(4MP)

        Returns:
            [{id, width, height, url, photographer, alt, avg_color, src: {original, large, medium, small}}]
        """
        params = {
            "query": query,
            "per_page": per_page,
            "page": page,
            "orientation": orientation,
            "size": size,
            "locale": locale,
        }
        try:
            resp = await self.client.get("/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            photos = data.get("photos", [])
            logger.info(
                "Pexels: searched '%s' → %d photos (total_results=%d)",
                query, len(photos), data.get("total_results", 0),
            )
            return photos
        except httpx.HTTPStatusError as e:
            logger.warning("Pexels search HTTP error: %s", e)
            return []
        except Exception as e:
            logger.warning("Pexels search failed: %s", e)
            return []

    async def search_multi_keywords(
        self,
        keywords: List[str],
        per_page: int = 3,
    ) -> List[Dict[str, Any]]:
        """并发搜索多个关键词，合并去重

        Args:
            keywords: 搜索关键词列表
            per_page: 每关键词获取数量

        Returns:
            去重后的图片列表
        """
        if not keywords:
            return []

        tasks = [self.search(kw, per_page=per_page) for kw in keywords[:5]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_ids = set()
        all_photos = []
        for result in results:
            if isinstance(result, Exception):
                continue
            for photo in result:
                pid = photo.get("id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_photos.append(photo)

        logger.info(
            "Pexels: multi-keyword search (%d keywords) → %d unique photos",
            len(keywords), len(all_photos),
        )
        return all_photos

    async def download_to_base64(
        self,
        photos: List[Dict[str, Any]],
        size: str = "large",
        max_images: int = 8,
    ) -> List[Dict[str, Any]]:
        """下载 Pexels 图片并编码为 base64

        Args:
            photos: Pexels 返回的图片对象列表
            size: 下载尺寸 (original / large / large2x / medium / small)
            max_images: 最多下载数量

        Returns:
            [{base64, title, source_url, width, height, photographer, pexels_id}]
        """
        results = []

        async def _download_one(photo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            src_obj = photo.get("src", {})
            url = src_obj.get(size) or src_obj.get("large") or src_obj.get("original")
            if not url:
                return None

            try:
                resp = await self.client.get(url, headers={})  # 不传 API key 到 CDN
                resp.raise_for_status()
                img_bytes = resp.content
                if len(img_bytes) < 1000:  # 太少视为无效
                    return None
                b64 = base64.b64encode(img_bytes).decode("ascii")
                return {
                    "base64": b64,
                    "title": photo.get("alt", ""),
                    "source_url": photo.get("url", ""),
                    "width": photo.get("width", 0),
                    "height": photo.get("height", 0),
                    "photographer": photo.get("photographer", ""),
                    "pexels_id": photo.get("id", 0),
                    "type": "pexels",
                }
            except Exception as e:
                logger.debug("Pexels download failed for %s: %s", url[:60], e)
                return None

        tasks = [_download_one(p) for p in photos[:max_images]]
        downloads = await asyncio.gather(*tasks, return_exceptions=True)

        for result in downloads:
            if isinstance(result, Exception):
                continue
            if result:
                results.append(result)

        logger.info(
            "Pexels: downloaded %d/%d images (size=%s)",
            len(results), len(photos[:max_images]), size,
        )
        return results

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()


# 模块级便捷函数
async def search_and_download(
    api_key: str,
    queries: List[str],
    per_query: int = 3,
    total_limit: int = 8,
) -> List[Dict[str, Any]]:
    """一站式: 搜索 + 下载 Pexels 图片

    Args:
        api_key: Pexels API Key
        queries: 搜索关键词列表
        per_query: 每关键词搜索数量
        total_limit: 总下载上限

    Returns:
        [{base64, title, source_url, ...}]
    """
    client = PexelsClient(api_key)
    try:
        photos = await client.search_multi_keywords(queries, per_page=per_query)
        if not photos:
            logger.warning("Pexels: no photos found for queries %s", queries)
            return []
        return await client.download_to_base64(photos, size="large", max_images=total_limit)
    finally:
        await client.close()
