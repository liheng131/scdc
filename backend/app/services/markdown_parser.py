"""
MarkdownPageParser —— Markdown 报告 → ReportPageModel 转换器

职责：
1. 解析 ReporterAgent 输出的 Markdown 报告
2. 按 ## 标题拆分章节
3. 提取 base64 内嵌图片 → ImageBlock
4. 提取正文段落 → TextBlock
5. 按 600 字/页 自动分页
6. 按布局提示分配 text_top / text_left / image_only / text_only
7. 输出标准 ReportPageModel

图片分配策略：
- 图片在 Markdown 中的位置 → 匹配到最近的正文页
- 每张正文页最多 2 张图片
- 图片多于正文页 → 多余的独立成 picture 页
- 正文页无图片 → 从章节配图中分配 1 张
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.report_page_model import (
    ReportPageModel, PageModel, TextBlock, ImageBlock, TableBlock,
    make_cover_page, make_toc_page, make_section_page,
    make_content_page, make_picture_page, make_summary_page,
    MAX_CHARS_PER_PAGE, MAX_IMAGES_PER_PAGE, DEFAULT_BG_COLOR,
)

logger = logging.getLogger(__name__)

# 匹配 base64 内嵌图片: ![alt](data:image/png;base64,...)
IMG_PATTERN = re.compile(
    r'!\[([^\]]*)\]\(data:image/(?:png|jpeg|jpg|gif|webp);base64,([A-Za-z0-9+/=\s]+)\)',
    re.DOTALL,
)

# 匹配 [CHART: type|dimension] 标记
CHART_PATTERN = re.compile(
    r'\[\s*CHART\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*([^\]]+?)\s*\]',
)

# 匹配 Markdown 表格行: | col1 | col2 | col3 |
TABLE_ROW_PATTERN = re.compile(
    r'^\|(.+)\|\s*$',
)

# 匹配表格分隔行: |---|---| 或 |:---|:---:|---:|
TABLE_SEP_PATTERN = re.compile(
    r'^\|[\s:]*[-]+[\s:]*\|[\s:]*[-]+[\s:]*(\|[\s:]*[-]+[\s:]*)*\|\s*$',
)


class MarkdownPageParser:
    """Markdown 报告 → ReportPageModel 转换器"""

    def __init__(self):
        self.max_chars_per_page = MAX_CHARS_PER_PAGE

    # ── 公开 API ──

    def parse(
        self,
        markdown: str,
        title: str = "报告",
        chart_images: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReportPageModel:
        """主入口：将 Markdown 报告解析为 ReportPageModel

        Args:
            markdown: ReporterAgent 输出的 Markdown 报告
            title: 报告标题
            chart_images: 章节配图列表 [{"section": str, "title": str, "base64": str, "position": int}]
            metadata: 额外元数据

        Returns:
            ReportPageModel 实例
        """
        if not markdown:
            markdown = ""

        pages: List[PageModel] = []
        sections = self._split_sections(markdown, title)

        # 1. 封面
        subtitle = self._extract_subtitle(markdown)
        pages.append(make_cover_page(title, subtitle))

        # 2. 目录
        section_titles = [s["title"] for s in sections]
        if section_titles:
            pages.append(make_toc_page(section_titles))

        # 3. 构建章节配图索引
        section_chart_index = self._build_chart_index(chart_images or [])

        # 4. 每个章节
        for sec_idx, section in enumerate(sections, start=1):
            sec_title = section["title"]
            sec_content = section["content"]

            # 4.1 章节封面
            pages.append(make_section_page(sec_title, sec_idx))

            # 4.2 从章节内容中提取内嵌图片和表格
            inline_images = self._extract_images(sec_content)
            # 提取表格，同时移除表格语法后的纯文本
            text_no_tables, sec_tables = self._extract_tables(sec_content)
            # 移除图片语法后的纯文本
            text_only = self._strip_images(text_no_tables)

            # 4.3 章节配图（按 section 名 + position 匹配合并去重）
            sec_charts: List[Dict[str, str]] = []
            seen_b64: set = set()
            # 先按 section 名匹配
            for chart in section_chart_index.get(sec_title, []):
                b64 = chart.get("base64", "")
                if b64 and b64 not in seen_b64:
                    seen_b64.add(b64)
                    sec_charts.append(chart)
            # 再按 position 匹配（只添加 section 名未匹配到的）
            for chart in (chart_images or []):
                if chart.get("position") == sec_idx:
                    b64 = chart.get("base64", "")
                    if b64 and b64 not in seen_b64:
                        seen_b64.add(b64)
                        sec_charts.append(chart)

            # 4.4 合并所有图片（全局去重：同一 base64 无论来源只保留一次）
            seen_b64: set = set()
            all_images: List[ImageBlock] = []
            for img in inline_images:
                if img.base64 and img.base64 not in seen_b64:
                    seen_b64.add(img.base64)
                    all_images.append(img)
            for img in self._charts_to_blocks(sec_charts):
                if img.base64 and img.base64 not in seen_b64:
                    seen_b64.add(img.base64)
                    all_images.append(img)

            # 4.5 正文分页并分配图片和表格
            content_pages = self._paginate_content(
                sec_title, sec_idx, text_only, all_images, tables=sec_tables,
            )
            pages.extend(content_pages)

        # 5. 总结
        summary_text = self._extract_summary_text(markdown, sections)
        summary_blocks = self._text_to_blocks(summary_text)
        pages.append(make_summary_page(summary_blocks))

        return ReportPageModel(
            title=title,
            pages=pages,
            metadata=metadata or {},
        )

    # ── 内部：章节拆分 ──

    def _split_sections(self, markdown: str, title: str) -> List[Dict[str, Any]]:
        """按 ## 标题拆分章节"""
        lines = markdown.split("\n")
        sections: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for raw in lines:
            line = raw.rstrip()
            if line.startswith("## "):
                if current is not None:
                    current["content"] = current["content"].strip()
                    sections.append(current)
                current = {"title": line[3:].strip(), "content": ""}
            elif line.startswith("# ") and not sections and current is None:
                title = line[2:].strip()
            else:
                if current is not None:
                    current["content"] += line + "\n"
                # else: ## 出现之前的内容丢弃

        if current is not None:
            current["content"] = current["content"].strip()
            sections.append(current)

        return sections

    # ── 内部：图片提取 ──

    def _extract_images(self, content: str) -> List[ImageBlock]:
        """从内容中提取 base64 内嵌图片"""
        images: List[ImageBlock] = []
        for m in IMG_PATTERN.finditer(content):
            alt = m.group(1).strip() or "图片"
            b64_data = re.sub(r'\s+', '', m.group(2))
            images.append(ImageBlock(
                base64=b64_data,
                alt=alt,
                width_ratio=0.85,
                max_height_inch=3.0,
                position="bottom",
            ))
        return images

    def _strip_images(self, content: str) -> str:
        """移除内容中的图片语法"""
        return IMG_PATTERN.sub('', content).strip()

    def _charts_to_blocks(self, charts: List[Dict[str, str]]) -> List[ImageBlock]:
        """将 chart_images 格式转换为 ImageBlock 列表"""
        blocks: List[ImageBlock] = []
        seen: set = set()
        for chart in charts:
            b64 = chart.get("base64", "")
            if not b64 or b64 in seen:
                continue
            seen.add(b64)
            blocks.append(ImageBlock(
                base64=b64,
                alt=chart.get("title", "图表"),
                width_ratio=0.85,
                max_height_inch=3.0,
                position="bottom",
            ))
        return blocks

    # ── 内部：表格提取 ──

    def _extract_tables(self, content: str) -> Tuple[str, List[TableBlock]]:
        """从 Markdown 内容中提取表格，返回 (纯文本, 表格列表)

        Markdown 表格格式:
            | Header 1 | Header 2 |
            |----------|----------|
            | Cell 1   | Cell 2   |
        """
        tables: List[TableBlock] = []
        lines = content.split("\n")
        cleaned_lines: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            # 检测表格起始: 当前行是表格行，且下一行是分隔行
            if TABLE_ROW_PATTERN.match(line) and i + 1 < len(lines) and TABLE_SEP_PATTERN.match(lines[i + 1].rstrip()):
                # 解析表头
                headers = self._parse_table_row(line)
                i += 2  # 跳过表头行和分隔行
                rows: List[List[str]] = []
                while i < len(lines) and TABLE_ROW_PATTERN.match(lines[i].rstrip()):
                    row = self._parse_table_row(lines[i].rstrip())
                    if row:
                        rows.append(row)
                    i += 1
                if headers or rows:
                    tables.append(TableBlock(headers=headers, rows=rows))
                continue
            cleaned_lines.append(lines[i])
            i += 1

        return "\n".join(cleaned_lines), tables

    @staticmethod
    def _parse_table_row(line: str) -> List[str]:
        """解析单行表格: | col1 | col2 | → ['col1', 'col2']"""
        # 去掉首尾的 |，按 | 分割
        cells = line.strip().strip("|").split("|")
        return [c.strip() for c in cells]

    # ── 内部：正文分页 ──

    def _paginate_content(
        self,
        section_title: str,
        section_number: int,
        text: str,
        images: List[ImageBlock],
        tables: Optional[List[TableBlock]] = None,
    ) -> List[PageModel]:
        """将章节正文按 600 字/页分页，并分配图片和表格"""
        pages: List[PageModel] = []
        if not text and not images and not tables:
            return pages

        tables = tables or []

        # 纯文本分页
        text_chunks = self._split_text(text)

        # 分配图片到正文页
        # 策略：每页最多 2 张图片，优先分配给有文字的页
        remaining_images = list(images)
        page_index = 0

        for chunk in text_chunks:
            page_images = []
            # 从剩余图片中取最多 2 张
            while remaining_images and len(page_images) < 2:
                page_images.append(remaining_images.pop(0))

            # 表格分配给第一页正文
            page_tables = tables if page_index == 0 else []

            blocks = self._text_to_blocks(chunk)
            pages.append(make_content_page(
                section_title=section_title,
                section_number=section_number,
                text_blocks=blocks,
                images=page_images,
                tables=page_tables,
                page_index=page_index,
            ))
            page_index += 1

        # 如果没有任何正文页但有表格，创建一页放表格
        if not pages and tables:
            pages.append(make_content_page(
                section_title=section_title,
                section_number=section_number,
                text_blocks=[],
                images=[],
                tables=tables,
                page_index=0,
            ))

        # 剩余的图片独立成 picture 页
        while remaining_images:
            batch = remaining_images[:MAX_IMAGES_PER_PAGE]
            remaining_images = remaining_images[MAX_IMAGES_PER_PAGE:]
            pages.append(make_picture_page(
                title=f"{section_title} - 图表",
                images=batch,
                section_number=section_number,
            ))

        # 如果没有任何页（空章节），至少生成一页
        if not pages and images:
            pages.append(make_picture_page(
                title=f"{section_title} - 图表",
                images=images[:MAX_IMAGES_PER_PAGE],
                section_number=section_number,
            ))

        return pages

    def _split_text(self, text: str) -> List[str]:
        """按 600 字/页 切分文本"""
        text = (text or "").strip()
        if not text:
            return [""]

        if len(text) <= self.max_chars_per_page:
            return [text]

        # 按段落切分
        paragraphs = re.split(r'\n\s*\n', text)
        all_blocks: List[str] = []
        for p in paragraphs:
            for sub in re.split(r'\n', p):
                sub = sub.strip()
                if sub:
                    all_blocks.append(sub)

        chunks: List[str] = []
        current = ""
        for block in all_blocks:
            tentative = (current + "\n" + block) if current else block
            if len(tentative) <= self.max_chars_per_page:
                current = tentative
            else:
                if current:
                    chunks.append(current)
                if len(block) > self.max_chars_per_page:
                    # 超长段落按句子切分
                    sub_chunks = self._split_long_block(block)
                    if len(sub_chunks) > 1:
                        chunks.extend(sub_chunks[:-1])
                        current = sub_chunks[-1]
                    else:
                        current = sub_chunks[0] if sub_chunks else ""
                else:
                    current = block
        if current:
            chunks.append(current)
        return chunks if chunks else [""]

    def _split_long_block(self, block: str) -> List[str]:
        """对超长段落按句子边界切分"""
        chunks: List[str] = []
        remaining = block
        while len(remaining) > self.max_chars_per_page:
            cut = -1
            for sep in ["。", "！", "？", "；", "\n", "，", "、", " "]:
                pos = remaining.rfind(sep, 0, self.max_chars_per_page)
                if pos > cut:
                    cut = pos + len(sep)
            if cut <= 0:
                cut = self.max_chars_per_page
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    # ── 内部：文本 → TextBlock ──

    def _text_to_blocks(self, text: str) -> List[TextBlock]:
        """将 Markdown 文本转为 TextBlock 列表"""
        if not text:
            return []

        blocks: List[TextBlock] = []
        # 移除图片语法
        text = self._strip_images(text)
        # 移除 CHART 标记
        text = CHART_PATTERN.sub('', text)

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("---"):
                continue
            # 跳过表格行（已被 _extract_tables 提取，但防止残留）
            if line.startswith("|") and line.endswith("|"):
                continue

            if line.startswith("### "):
                blocks.append(TextBlock(
                    text=line[4:], style="title", font_size=16,
                    bold=True, color="#1F3A5F",
                ))
            elif line.startswith("## "):
                blocks.append(TextBlock(
                    text=line[3:], style="title", font_size=18,
                    bold=True, color="#1F3A5F",
                ))
            elif line.startswith("> "):
                blocks.append(TextBlock(
                    text=line[2:], style="caption", font_size=13,
                    color="#666666",
                ))
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append(TextBlock(
                    text="• " + line[2:], style="bullet", font_size=14,
                ))
            elif re.match(r'^\d+[\.\)]\s', line):
                blocks.append(TextBlock(
                    text=line, style="bullet", font_size=14,
                ))
            else:
                blocks.append(TextBlock(
                    text=line, style="body", font_size=14,
                ))

        return blocks

    # ── 内部：辅助 ──

    def _extract_subtitle(self, markdown: str) -> str:
        """从 Markdown 中提取副标题/日期"""
        for line in markdown.split("\n"):
            line = line.strip()
            if line.startswith("> **执行时间**:"):
                return line.lstrip("> ").strip()
        return ""

    def _extract_summary_text(
        self,
        markdown: str,
        sections: List[Dict[str, Any]],
    ) -> str:
        """提取总结文本"""
        for sec in reversed(sections):
            title_lower = sec["title"].lower()
            if any(kw in title_lower for kw in ["总结", "建议", "展望", "conclusion"]):
                return sec["content"]
        # 取最后一个章节的内容
        if sections:
            return sections[-1]["content"]
        return ""

    def _build_chart_index(
        self,
        chart_images: List[Dict[str, str]],
    ) -> Dict[str, List[Dict[str, str]]]:
        """按 section 名称构建配图索引"""
        index: Dict[str, List[Dict[str, str]]] = {}
        for ci in chart_images:
            section = (ci.get("section") or "").strip()
            if section:
                index.setdefault(section, []).append(ci)
        return index


# 模块级常量（从 report_page_model 导入的，方便外部使用）
_MAX_IMAGES_PER_PAGE = 3  # noqa: F841