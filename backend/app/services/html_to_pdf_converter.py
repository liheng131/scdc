"""
HTML → PDF 转换器

使用Playwright原生PDF导出功能
"""

import logging

from app.services.playwright_renderer import PlaywrightRenderer

logger = logging.getLogger(__name__)


class HTMLToPDFConverter:
    """
    HTML → PDF转换器
    
    使用Playwright将HTML渲染为PDF，保持视觉质量。
    """
    
    def __init__(self):
        self.renderer = PlaywrightRenderer()
    
    async def convert(self, html: str, output_path: str):
        """
        将HTML转换为PDF
        
        Args:
            html: 完整的HTML字符串
            output_path: PDF输出路径
        """
        logger.info("Rendering HTML to PDF...")
        await self.renderer.render_to_pdf(html, output_path)
        logger.info(f"PDF saved: {output_path}")
