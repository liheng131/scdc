"""
图像生成服务

提供与 ComfyUI 图像生成服务的集成，支持：
- 连接 ComfyUI API 服务器
- 提交图像生成请求
- 轮询生成状态
- 获取生成的图片 URL
"""

import asyncio
import logging
import aiohttp
from typing import Optional, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class ImageGenerationService:
    """ComfyUI 图像生成服务"""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or getattr(settings, 'comfyui_base_url', 'http://localhost:8188')
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "low quality, blurry, distorted, watermark, text, signature",
        width: int = 1024,
        height: int = 768,
        steps: int = 20,
        cfg_scale: float = 7.0,
        seed: int = -1,
        timeout: int = 120
    ) -> Optional[Dict[str, Any]]:
        """
        生成单张图片

        Args:
            prompt: 图像描述提示词（英文）
            negative_prompt: 负面提示词
            width: 图片宽度
            height: 图片高度
            steps: 生成步数
            cfg_scale: 引导强度
            seed: 随机种子（-1 为随机）
            timeout: 超时时间（秒）

        Returns:
            生成结果字典，包含 image_url 等信息，失败返回 None
        """
        try:
            session = await self._get_session()

            # 构建 ComfyUI API 请求体
            workflow = self._build_workflow(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                seed=seed
            )

            # 提交生成任务
            async with session.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow}
            ) as resp:
                if resp.status != 200:
                    logger.error(f"ComfyUI prompt API returned status {resp.status}")
                    return None
                result = await resp.json()
                prompt_id = result.get("prompt_id")

            if not prompt_id:
                logger.error("No prompt_id returned from ComfyUI")
                return None

            # 轮询等待生成完成
            image_url = await self._wait_for_completion(prompt_id, timeout)
            
            if image_url:
                return {
                    "image_url": image_url,
                    "prompt": prompt,
                    "width": width,
                    "height": height
                }
            
            return None

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return None

    def _build_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int
    ) -> Dict[str, Any]:
        """
        构建 ComfyUI 工作流 JSON
        
        使用标准的 SDXL/SD1.5 工作流模板
        """
        import random
        
        if seed == -1:
            seed = random.randint(0, 2**32 - 1)

        # 标准 ComfyUI 工作流
        workflow = {
            "4": {
                "inputs": {
                    "ckpt_name": "v1-5-pruned-emaonly.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "8": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode"
            },
            "9": {
                "inputs": {
                    "filename_prefix": "ComfyUI",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            },
            "3": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            }
        }

        return workflow

    async def _wait_for_completion(
        self,
        prompt_id: str,
        timeout: int = 120,
        poll_interval: float = 2.0
    ) -> Optional[str]:
        """
        轮询等待图像生成完成

        Returns:
            图片 URL 或 None
        """
        session = await self._get_session()
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                async with session.get(
                    f"{self.base_url}/history/{prompt_id}"
                ) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    history = await resp.json()
                    
                    if prompt_id not in history:
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    prompt_history = history[prompt_id]
                    status = prompt_history.get("status", {})
                    
                    if status.get("status_str") == "error":
                        logger.error(f"ComfyUI generation failed: {status}")
                        return None
                    
                    if status.get("completed", False):
                        # 提取生成的图片信息
                        outputs = prompt_history.get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                for img_info in node_output["images"]:
                                    filename = img_info.get("filename")
                                    if filename:
                                        return f"{self.base_url}/view?filename={filename}"
                        
                        logger.warning("No image found in ComfyUI output")
                        return None

            except Exception as e:
                logger.warning(f"Error polling ComfyUI status: {e}")

            await asyncio.sleep(poll_interval)

        logger.error(f"ComfyUI generation timed out after {timeout}s")
        return None
