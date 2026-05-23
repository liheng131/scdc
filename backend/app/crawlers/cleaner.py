"""
HTML 内容清洗器

从原始 HTML 中提取标题、纯文本内容和元数据，去除噪声元素。

为什么需要清洗：
- CollectorAgent 爬取的原始 HTML 包含大量无关内容（脚本、样式、导航栏）
- LLM 对输入 token 数量敏感，去除噪声可降低 API 调用成本
- 纯文本格式更易于后续 CleanerAgent 做语义理解和摘要提取

为什么要 skip 而不是 simple remove：
- decompose() 彻底删除标签和内容，避免 get_text() 时残留 inline JS
- script/style/nav/footer/header/iframe/noscript 这些标签内容通常为噪声
"""

from bs4 import BeautifulSoup
from typing import Dict, Any, Tuple

class HTMLCleaner:
    @staticmethod
    def clean(raw_html: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        清洗 HTML 为结构化数据

        返回:
            (标题, 清洗后的纯文本, 元数据字典包含 description/keywords 等)
        """
        if not raw_html or not raw_html.strip():
            return "", "", {}

        soup = BeautifulSoup(raw_html, "html.parser")

        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        metadata = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                metadata[name] = content

        for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
            element.decompose()

        lines = [line.strip() for line in soup.get_text().splitlines()]
        clean_text = "\n".join([line for line in lines if line])

        return title, clean_text, metadata
