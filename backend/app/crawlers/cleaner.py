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

import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Tuple


class HTMLCleaner:
    # 模板语法标记:Vue {{ }} / Vue v-* 属性残留 / Angular {{ }} / React 注入 HTML 等
    _TEMPLATE_TOKEN_RE = re.compile(r"\{\{[^}]*\}\}|v-[a-z]+(?:-[a-z]+)*=|ng-[a-z]+=")
    # 替换字符(中文 / 英文 / 数字 / 标点 / 空白以外)密度阈值
    _GARBAGE_RATIO_THRESHOLD = 0.30  # 替换字符占比 > 30% 视为乱码
    # PDF 二进制对象头(常见于 PDF 文本提取失败时的残留)
    _PDF_OBJ_RE = re.compile(r"%PDF-\d+\.\d+|endobj|<<\s*/[A-Za-z]+\s+\d+\s*>>")

    @staticmethod
    def _is_garbled(text: str) -> bool:
        """
        启发式:返回 True 表示清洗后的文本几乎肯定是乱码(应该丢弃、走 snippet 降级)。

        判定规则（任一命中即视为乱码）:
        1. 含 PDF/OOXML 残留标记（说明响应其实是二进制）
        2. 含高密度 Vue/Angular 模板语法（说明是 SPA 没渲染）
        3. CJK 字符极少 + 控制字符/非打印字符占比过高（说明 utf-8 解码失败）
        """
        if not text:
            return True

        # 规则 1: PDF 残留
        if HTMLCleaner._PDF_OBJ_RE.search(text):
            return True

        # 规则 2: 模板语法密度 (>5% 的字符是模板标记)
        tmpl_matches = HTMLCleaner._TEMPLATE_TOKEN_RE.findall(text)
        if len(text) > 200 and len("".join(tmpl_matches)) / len(text) > 0.05:
            return True

        # 规则 3: 不可打印字符比例
        sample = text[:2000]  # 取前 2000 字符够快
        if sample:
            printable = sum(
                1 for c in sample
                if c.isprintable() or c in "\n\r\t"
            )
            ratio = printable / len(sample)
            if ratio < 1.0 - HTMLCleaner._GARBAGE_RATIO_THRESHOLD:
                return True
        return False

    @staticmethod
    def clean(raw_html: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        清洗 HTML 为结构化数据

        返回:
            (标题, 清洗后的纯文本, 元数据字典包含 description/keywords 等)

        行为变化(Phase 7 修复):
        - 乱码 PDF / SPA 模板残留时返回空 clean_text,让 CollectorAgent 走 snippet 降级
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

        # Phase 7: 启发式判乱码,命中则丢弃让上层走 snippet
        if HTMLCleaner._is_garbled(clean_text):
            return title or "", "", metadata

        return title, clean_text, metadata

