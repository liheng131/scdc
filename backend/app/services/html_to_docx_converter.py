"""
HTML → Word 转换器

流程：
1. 用BeautifulSoup解析HTML
2. 提取结构化内容（标题、段落、表格、图片）
3. 用python-docx生成Word文档
"""

import base64
import logging
import os
import tempfile

import docx
import docx.shared
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class HTMLToDOCXConverter:
    """
    HTML → Word转换器
    
    从HTML提取结构化内容，生成Word文档。
    内容质量高，但视觉排版不如PDF/PPT。
    """
    
    async def convert(self, html: str, output_path: str):
        """
        将HTML转换为Word文档
        
        Args:
            html: 完整的HTML字符串
            output_path: Word输出路径
        """
        logger.info("Converting HTML to Word...")
        
        soup = BeautifulSoup(html, 'html.parser')
        
        doc = docx.Document()
        
        # 遍历所有slide（HTML生成器输出的是 <section class="slide">）
        slides = soup.find_all('section', class_='slide')
        
        if not slides:
            logger.warning("No .slide elements found, using body content")
            slides = [soup.body] if soup.body else [soup]
        
        for i, slide in enumerate(slides):
            logger.debug(f"Processing slide {i+1}/{len(slides)}")
            
            # 提取标题
            h2 = slide.find('h2')
            if h2:
                doc.add_heading(h2.get_text(), level=1)
            
            # 提取段落
            paragraphs = slide.find_all('p')
            for p in paragraphs:
                text = p.get_text()
                if text.strip():
                    doc.add_paragraph(text)
            
            # 提取表格
            tables = slide.find_all('table')
            for table in tables:
                self._add_table_to_doc(doc, table)
            
            # 提取图片
            images = slide.find_all('img')
            for img in images:
                await self._add_image_to_doc(doc, img)
            
            # 分页（除了最后一页）
            if i < len(slides) - 1:
                doc.add_page_break()
        
        doc.save(output_path)
        logger.info(f"Word document saved: {output_path}")
    
    def _add_table_to_doc(self, doc, html_table):
        """将HTML表格转换为Word表格"""
        rows = html_table.find_all('tr')
        if not rows:
            return
        
        # 确定表格尺寸
        num_cols = len(rows[0].find_all(['th', 'td']))
        table = doc.add_table(rows=len(rows), cols=num_cols)
        table.style = 'Table Grid'
        
        # 填充数据
        for i, row in enumerate(rows):
            cells = row.find_all(['th', 'td'])
            for j, cell in enumerate(cells):
                table.rows[i].cells[j].text = cell.get_text()
    
    async def _add_image_to_doc(self, doc, img_tag):
        """将HTML图片添加到Word文档"""
        src = img_tag.get('src', '')
        
        if src.startswith('data:image'):
            # 从base64解码
            try:
                header, encoded = src.split(',', 1)
                image_data = base64.b64decode(encoded)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                    tmp.write(image_data)
                    tmp_path = tmp.name
                
                try:
                    doc.add_picture(tmp_path, width=docx.shared.Inches(5))
                finally:
                    os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to add image to Word: {e}")
        elif src.startswith('http'):
            # 网络图片暂不处理
            logger.debug(f"Skipping network image: {src}")
