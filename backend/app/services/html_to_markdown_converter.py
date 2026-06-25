"""
HTML → Markdown 转换器

从HTML提取结构化内容，生成干净的Markdown
"""

import logging

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class HTMLToMarkdownConverter:
    """
    HTML → Markdown转换器
    
    从HTML提取结构化内容，生成干净的Markdown格式。
    """
    
    async def convert(self, html: str, output_path: str):
        """
        将HTML转换为Markdown
        
        Args:
            html: 完整的HTML字符串
            output_path: Markdown输出路径
        """
        logger.info("Converting HTML to Markdown...")
        
        soup = BeautifulSoup(html, 'html.parser')
        
        markdown_lines = []
        
        slides = soup.find_all('section', class_='slide')
        
        if not slides:
            logger.warning("No .slide elements found, using body content")
            slides = [soup.body] if soup.body else [soup]
        
        for i, slide in enumerate(slides):
            logger.debug(f"Processing slide {i+1}/{len(slides)}")
            
            # 提取标题
            h2 = slide.find('h2')
            if h2:
                markdown_lines.append(f'# {h2.get_text()}\n')
            
            # 提取段落
            paragraphs = slide.find_all('p')
            for p in paragraphs:
                text = p.get_text().strip()
                if text:
                    markdown_lines.append(f'{text}\n')
            
            # 提取表格
            tables = slide.find_all('table')
            for table in tables:
                markdown_lines.append(self._table_to_markdown(table))
            
            # 提取图片（仅保留alt文本）
            images = slide.find_all('img')
            for img in images:
                alt = img.get('alt', '图片')
                markdown_lines.append(f'![{alt}](image_url)\n')
            
            # 分隔符（除了最后一页）
            if i < len(slides) - 1:
                markdown_lines.append('\n---\n')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(markdown_lines))
        
        logger.info(f"Markdown saved: {output_path}")
    
    def _table_to_markdown(self, html_table) -> str:
        """将HTML表格转换为Markdown表格"""
        rows = html_table.find_all('tr')
        if not rows:
            return ''
        
        markdown_rows = []
        for i, row in enumerate(rows):
            cells = row.find_all(['th', 'td'])
            cell_texts = [cell.get_text().strip() for cell in cells]
            markdown_rows.append('| ' + ' | '.join(cell_texts) + ' |')
            
            # 在第一行后添加分隔符
            if i == 0:
                markdown_rows.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
        
        return '\n'.join(markdown_rows) + '\n'
