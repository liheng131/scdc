"""
HTML → Markdown 转换器 (v2)

v2: 图片以 base64 data URL 内嵌（不是链接格式），保留表格和段落结构
v1: 图片输出为 ![alt](image_url) 链接格式
"""

import logging

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class HTMLToMarkdownConverter:
    """HTML → Markdown 转换器 (v2: base64 图片内嵌)"""

    async def convert(self, html: str, output_path: str):
        """将 HTML 转换为 Markdown

        Args:
            html: 完整的 HTML 字符串
            output_path: Markdown 输出路径
        """
        logger.info("Converting HTML to Markdown (v2: inline base64 images)...")

        soup = BeautifulSoup(html, "html.parser")
        markdown_lines = []

        # 全局标题
        title_tag = soup.find("title")
        if title_tag:
            markdown_lines.append(f"# {title_tag.get_text()}\n")

        slides = soup.find_all("section", class_="slide")
        if not slides:
            logger.warning("No .slide elements found, using body content")
            slides = [soup.body] if soup.body else [soup]

        for i, slide in enumerate(slides):
            # 跳过 notes
            notes = slide.find("div", class_="notes")
            if notes:
                notes.extract()

            # 标题
            h2 = slide.find("h2")
            title_tag_found = h2
            if title_tag_found:
                title_text = title_tag_found.get_text(strip=True)
                if title_text:
                    markdown_lines.append(f"\n## {title_text}\n")

            # 段落
            for p_tag in slide.find_all("p"):
                # 跳过 notes 中的段落
                if p_tag.find_parent("div", class_="notes"):
                    continue
                text = p_tag.get_text(strip=True)
                if text:
                    # 检查是否是 lede 段落
                    cls = p_tag.get("class", [])
                    if "lede" in cls:
                        markdown_lines.append(f"> {text}\n")
                    elif "kicker" in cls:
                        markdown_lines.append(f"**{text}**\n")
                    else:
                        markdown_lines.append(f"{text}\n")

            # 图片：内嵌 base64 data URL
            for img_tag in slide.find_all("img"):
                src = img_tag.get("src", "")
                alt = img_tag.get("alt", "")
                if src:
                    # 保留原始 src（包括 data:image/png;base64,...）
                    markdown_lines.append(f"![{alt}]({src})\n")

            # 表格
            for table_tag in slide.find_all("table"):
                markdown_lines.append(self._table_to_markdown(table_tag))
                markdown_lines.append("")

            # 分隔符（除了最后一页）
            if i < len(slides) - 1:
                markdown_lines.append("\n---\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(markdown_lines))

        logger.info(f"Markdown saved: {output_path}")

    def _table_to_markdown(self, html_table) -> str:
        """将 HTML 表格转换为 Markdown 表格"""
        rows = html_table.find_all("tr")
        if not rows:
            return ""

        markdown_rows = []
        for i, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            markdown_rows.append("| " + " | ".join(cell_texts) + " |")

            # 在第一行后添加分隔符
            if i == 0:
                markdown_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

        return "\n".join(markdown_rows) + "\n"
