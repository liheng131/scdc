"""
WebImageExtractor（网页截图提取服务）

职责：
- 使用 Playwright 对指定 URL 列表进行截图
- 提取页面标题等元数据
- 返回 base64 编码的截图列表，供报告生成流水线使用
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from app.services.playwright_renderer import PlaywrightRenderer

logger = logging.getLogger(__name__)


class WebImageExtractor:
    """
    网页截图提取服务

    使用 PlaywrightRenderer 对给定 URL 列表进行截图，
    提取页面标题等信息，返回 base64 编码的截图数据。
    """

    def __init__(self, renderer: Optional[PlaywrightRenderer] = None):
        self.renderer = renderer or PlaywrightRenderer()

    async def extract_chart_screenshots(
        self,
        urls: List[str],
        max_images: int = 10,
        timeout: int = 30000,
    ) -> List[Dict[str, Any]]:
        """
        对 URL 列表进行截图并返回 base64 数据。

        Args:
            urls: 要截图的 URL 列表
            max_images: 最多截取的图片数量
            timeout: 每个页面的超时时间（毫秒）

        Returns:
            列表，每个元素是一个字典，包含：
            - url: 截图对应的 URL
            - title: 页面标题
            - base64: 截图的 base64 编码字符串
            - source_url: 原始 URL
            - type: 固定为 "web_screenshot"
        """
        await self.renderer.initialize()

        results: List[Dict[str, Any]] = []
        urls_to_process = urls[:max_images]

        for url in urls_to_process:
            try:
                result = await self._capture_single_page(url, timeout)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to capture screenshot for {url}: {e}")

        logger.info(f"Captured {len(results)}/{len(urls_to_process)} screenshots")
        return results

    async def _capture_single_page(
        self, url: str, timeout: int
    ) -> Optional[Dict[str, Any]]:
        """截取单个页面的截图。"""
        page = await self.renderer.browser.new_page(
            viewport={"width": 1920, "height": 1080}
        )
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            await page.wait_for_timeout(1000)

            title = await page.title()
            screenshot_bytes = await page.screenshot(type="png", full_page=False)
            b64_str = base64.b64encode(screenshot_bytes).decode("utf-8")

            return {
                "url": url,
                "title": title or "",
                "base64": b64_str,
                "source_url": url,
                "type": "web_screenshot",
            }
        except Exception as e:
            logger.warning(f"Screenshot capture failed for {url}: {e}")
            return None
        finally:
            await page.close()


# Module-level singleton
web_image_extractor = WebImageExtractor()
