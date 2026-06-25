"""
HTML → PPT 转换器

流程：
1. 用Playwright将HTML每页渲染为截图
2. 创建PPT，每页插入一张全屏截图
"""

import logging
import os
import tempfile
from typing import Optional

from pptx import Presentation
from pptx.util import Inches, Pt

from app.services.playwright_renderer import PlaywrightRenderer

logger = logging.getLogger(__name__)


class HTMLToPPTConverter:
    """
    HTML → PPT转换器
    
    将HTML演示文稿转换为PPT格式。
    每页HTML渲染为截图后插入PPT，保持视觉质量。
    """
    
    def __init__(self):
        self.renderer = PlaywrightRenderer()
    
    async def convert(
        self, 
        html: str, 
        output_path: str, 
        template_id: Optional[str] = None
    ):
        """
        将HTML转换为PPT
        
        Args:
            html: 完整的HTML字符串
            output_path: PPT输出路径
            template_id: PPT模板ID（可选，用于添加母版）
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 渲染截图
            logger.info("Rendering HTML to screenshots...")
            screenshot_paths = await self.renderer.render_to_screenshots(html, tmpdir)
            
            if not screenshot_paths:
                raise ValueError("No screenshots generated from HTML")
            
            logger.info(f"Generated {len(screenshot_paths)} screenshots")
            
            # 2. 创建PPT
            prs = Presentation()
            
            # 如果指定了模板，应用模板
            if template_id:
                self._apply_template(prs, template_id)
            
            # 3. 每页插入截图
            for i, screenshot_path in enumerate(screenshot_paths):
                logger.debug(f"Adding slide {i+1}/{len(screenshot_paths)}")
                
                # 使用空白布局
                slide_layout = prs.slide_layouts[6]  # 空白布局
                slide = prs.slides.add_slide(slide_layout)
                
                # 插入全屏图片
                slide.shapes.add_picture(
                    screenshot_path,
                    left=0,
                    top=0,
                    width=prs.slide_width,
                    height=prs.slide_height
                )
            
            # 4. 保存PPT
            prs.save(output_path)
            logger.info(f"PPT saved: {output_path}")
    
    def _apply_template(self, prs: Presentation, template_id: str):
        """
        应用PPT模板（占位实现）

        ⚠️ NOT IMPLEMENTED: 当前 HTML 流程的 PPT 母版样式尚未实现.
        调用方传入 template_id 时, 此方法仅记录 WARN, 不影响生成结果.

        实现路线 (后续):
        1. 从 backend/data/pptx/template_<id>.pptx 读取母版
        2. 用 Presentation(template_path) 替换 prs 的 slide_masters
        3. 或逐张 slide 应用 layouts[template_id]

        替代方案: 旧 export_report 路径 (use_html_pipeline=false) 使用
        PPTTemplateService.fill_template_from_model 真正支持模板, 用户可临时回退.
        """
        logger.warning(
            "PPT template_id=%r is ignored by HTML pipeline (not implemented). "
            "Output PPT will use python-pptx default blank layout. "
            "Fallback: use use_html_pipeline=false for template support.",
            template_id,
        )
