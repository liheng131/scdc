"""
HTML 报告生成器 —— 基于 html-ppt 设计系统

设计系统来源：
- assets/base.css (tokens + primitives)
- assets/runtime.js (键盘导航、主题切换、演讲者模式)
- assets/themes/*.css (36 套主题)
- assets/animations/animations.css (27 种 CSS 动画)
- assets/fonts.css (webfonts)

输出 HTML 直接引用 /static/html-ppt/assets/* 路径，
由 Playwright 加载渲染。
"""

import html as html_lib
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LayoutType(str, Enum):
    """布局类型 —— 对应 html-ppt 的页面类型"""
    COVER = "cover"                   # 封面
    TOC = "toc"                       # 目录
    SECTION = "section"               # 章节封面
    CONTENT = "content"               # 通用内容（图+文）
    BULLETS = "bullets"               # 项目符号列表
    KPI_GRID = "kpi_grid"             # KPI 卡片网格
    TWO_COLUMN = "two_column"         # 双栏对比
    THREE_COLUMN = "three_column"     # 三列卡片
    TABLE = "table"                   # 数据表格
    IMAGE_HERO = "image_hero"         # 大图背景
    IMAGE_GRID = "image_grid"         # 图片网格
    STAT_HIGHLIGHT = "stat"           # 大数字
    CHART_BAR = "chart_bar"           # 柱状图
    CHART_LINE = "chart_line"         # 折线图
    CHART_PIE = "chart_pie"           # 饼图
    THANKS = "thanks"                 # 结尾致谢


class HTMLTextBlock(BaseModel):
    """HTML文本块"""
    text: str
    emphasis: List[str] = Field(default_factory=list)
    is_bullet: bool = False
    is_lead: bool = False  # lede 段（大字号简介）


class HTMLImageBlock(BaseModel):
    """HTML图片块"""
    url: str
    caption: str = ""
    source: str = ""


class HTMLPageModel(BaseModel):
    """HTML页面模型"""
    title: str
    layout: LayoutType = LayoutType.CONTENT
    kicker: str = ""
    text_blocks: List[HTMLTextBlock] = Field(default_factory=list)
    image_blocks: List[HTMLImageBlock] = Field(default_factory=list)
    kpi_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    table_data: Optional[Dict[str, Any]] = None
    chart_data: Optional[Dict[str, Any]] = None  # Chart.js 图表配置
    notes: str = ""  # 演讲者备注（runtime.js 的 S 键可见）


class HTMLReportGenerator:
    """
    生成基于 html-ppt 设计系统的高质量 HTML 演示文稿

    生成的 HTML 引用 /static/html-ppt/assets/ 下的 CSS/JS 资源，
    支持运行时主题切换、键盘导航、动画演示。
    """

    def __init__(self, theme: str = "minimal-white", static_base: str = "/static/html-ppt", use_absolute_paths: bool = False):
        self.theme = theme
        self.static_base = static_base.rstrip("/")
        self.use_absolute_paths = use_absolute_paths
        # 检测可用主题
        self.available_themes = self._scan_themes()

    def _assets_relpath(self) -> str:
        """生成资源路径

        - use_absolute_paths=True: 返回绝对路径 /static/html-ppt/assets，用于 iframe 预览（blob URL 场景）
        - use_absolute_paths=False: 返回相对路径 assets，用于 file:// 协议（Playwright 渲染/导出场景）
        """
        if self.use_absolute_paths:
            return f"{self.static_base}/assets"
        return "assets"  # HTML 存到临时文件后, assets 与 HTML 同级目录

    def _scan_themes(self) -> List[str]:
        """扫描可用主题"""
        import os
        # __file__ = app/services/html_report_generator.py
        # dirname x2 = app/  (这是 static/html-ppt/assets/themes 的父目录)
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "static", "html-ppt", "assets", "themes"
        )
        if not os.path.exists(themes_dir):
            return ["minimal-white"]
        return [
            f[:-4] for f in os.listdir(themes_dir)
            if f.endswith(".css")
        ]

    def generate(self, page_models: List[HTMLPageModel]) -> str:
        """生成完整 HTML 演示文稿

        Args:
            page_models: 结构化页面描述列表

        Returns:
            完整 HTML 字符串（含 html-ppt 资源引用）
        """
        slides_html_parts = []
        total = len(page_models)
        for idx, page in enumerate(page_models):
            slide_html = self._render_slide(page, idx, total)
            slides_html_parts.append(slide_html)

        slides_html = "\n".join(slides_html_parts)
        # 全部 36 套主题都写入 data-themes, runtime.js T 键循环时可在全部主题间切换
        themes_csv = ",".join(self.available_themes)

        return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{self.theme}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>研究报告</title>
<link rel="stylesheet" href="{self._assets_relpath()}/fonts.css">
<link rel="stylesheet" href="{self._assets_relpath()}/base.css">
<link rel="stylesheet" id="theme-link" href="{self._assets_relpath()}/themes/{self.theme}.css">
<link rel="stylesheet" href="{self._assets_relpath()}/animations/animations.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
/* === 单 deck 私有样式 === */
body {{ background: var(--bg); }}
.tbl {{
  width: 100%;
  border-collapse: collapse;
  font-size: 16px;
  background: var(--surface);
  border-radius: var(--radius);
  overflow: hidden;
}}
.tbl th, .tbl td {{
  padding: 14px 18px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}}
.tbl th {{
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--text-3);
  font-weight: 600;
  background: var(--surface-2);
}}
.tbl tr:hover td {{ background: var(--surface-2); }}
.tbl td.num {{ font-variant-numeric: tabular-nums; text-align: right; }}
.tbl td.up {{ color: var(--good); font-weight: 600; }}
.tbl td.dn {{ color: var(--bad); font-weight: 600; }}
.tbl-wrap {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px;
  box-shadow: var(--shadow);
}}
.hero-img {{
  width: 100%;
  height: 360px;
  object-fit: contain;
  background: var(--surface-2);
  border-radius: var(--radius);
  padding: 16px;
}}
.image-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow);
}}
.image-card img {{
  width: 100%;
  height: 240px;
  object-fit: contain;
  background: var(--surface-2);
  padding: 12px;
}}
.image-card .caption {{
  padding: 12px 18px;
  font-size: 13px;
  color: var(--text-2);
  border-top: 1px solid var(--border);
}}
.bullet-list {{
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}
.bullet-list li {{
  position: relative;
  padding: 16px 20px 16px 48px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-sm);
  font-size: 18px;
  line-height: 1.6;
}}
.bullet-list li::before {{
  content: '';
  position: absolute;
  left: 20px;
  top: 50%;
  transform: translateY(-50%);
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
}}
.section-page {{
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}}
.section-page .h1 {{
  font-size: 112px;
  line-height: 1.05;
  background: var(--grad);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.divider-accent {{
  width: 80px;
  height: 4px;
  background: var(--accent);
  margin: 18px 0;
  border-radius: 2px;
}}
</style>
</head>
<body data-themes="{themes_csv}" data-theme-base="{self._assets_relpath()}/themes/">
<div class="deck">
{slides_html}
</div>
<script src="{self._assets_relpath()}/runtime.js"></script>
<script src="{self._assets_relpath()}/animations/fx-runtime.js" defer></script>
</body>
</html>"""

    # ── 单页渲染 ──

    def _render_slide(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """根据布局类型分派到具体渲染器"""
        renderers = {
            LayoutType.COVER: self._render_cover,
            LayoutType.TOC: self._render_toc,
            LayoutType.SECTION: self._render_section,
            LayoutType.BULLETS: self._render_bullets,
            LayoutType.KPI_GRID: self._render_kpi_grid,
            LayoutType.TWO_COLUMN: self._render_two_column,
            LayoutType.THREE_COLUMN: self._render_three_column,
            LayoutType.TABLE: self._render_table,
            LayoutType.IMAGE_HERO: self._render_image_hero,
            LayoutType.IMAGE_GRID: self._render_image_grid,
            LayoutType.STAT_HIGHLIGHT: self._render_stat,
            LayoutType.THANKS: self._render_thanks,
            LayoutType.CHART_BAR: self._render_chart_page,
            LayoutType.CHART_LINE: self._render_chart_page,
            LayoutType.CHART_PIE: self._render_chart_page,
            LayoutType.CONTENT: self._render_content,
        }
        renderer = renderers.get(page.layout, self._render_content)
        return renderer(page, idx, total)

    def _wrap_slide(self, page: HTMLPageModel, idx: int, total: int, body: str, extra_class: str = "") -> str:
        """包装单页 slide 公共外壳"""
        active = " is-active" if idx == 0 else ""
        cls = f"slide{active}{(' ' + extra_class) if extra_class else ''}"
        notes = f'\n  <div class="notes">{html_lib.escape(page.notes or page.title)}</div>' if page.notes or page.title else ""
        # 章节内连续页不需要重复 footer
        return f'''<section class="{cls}" data-title="{html_lib.escape(page.title)}" data-index="{idx}">
  {body}{notes}
</section>'''

    def _esc(self, s: str) -> str:
        """HTML 转义"""
        return html_lib.escape(s or "")

    def _emphasize(self, text: str, keywords: List[str]) -> str:
        """高亮关键词"""
        result = self._esc(text)
        for kw in keywords or []:
            kw_esc = self._esc(kw)
            result = result.replace(kw_esc, f"<strong style='color:var(--accent)'>{kw_esc}</strong>")
        return result

    # ── 各种布局渲染器 ──

    def _render_cover(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """封面页（gradient-text + lede + pill）"""
        kicker = self._esc(page.kicker or "研究报告")
        title = self._esc(page.title)
        lede = ""
        if page.text_blocks:
            lede_text = page.text_blocks[0].text
            lede = f'<p class="lede anim-fade-up" data-anim="fade-up">{self._esc(lede_text)}</p>'

        pills = ""
        for i, tb in enumerate(page.text_blocks[1:4] if len(page.text_blocks) > 1 else []):
            pills += f'<span class="pill">{self._esc(tb.text)}</span>'

        body = f'''<div class="deck-header"><span class="eyebrow">Research Report</span><span class="eyebrow">{self._esc(str(idx + 1))} / {total}</span></div>
  <div class="anim-stagger-list" data-anim-target>
    <p class="kicker">{kicker}</p>
    <h1 class="h1 anim-fade-up" data-anim="fade-up">
      {title}
    </h1>
    {lede}
    <div class="row wrap mt-l">{pills}</div>
  </div>
  <div class="deck-footer">
    <span class="dim2">研究报告</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_toc(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """目录页（卡片网格）"""
        kicker = self._esc(page.kicker or "Contents")
        title = self._esc(page.title)

        cards = ""
        for i, tb in enumerate(page.text_blocks[:12], start=1):
            num = f"{i:02d}"
            cards += f'''<div class="card anim-fade-up" data-anim="fade-up" style="animation-delay:{i * 60}ms">
        <div class="row">
          <div class="h3 dim2" style="width:56px">{num}</div>
          <div><h4 class="mt-0">{self._emphasize(tb.text, tb.emphasis)}</h4></div>
        </div>
      </div>'''

        body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="grid g2 mt-l anim-stagger-list" data-anim-target>
    {cards}
  </div>
  <div class="deck-footer">
    <span class="dim2">目录</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_section(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """章节封面（渐变大标题）"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or f"Section · {idx + 1:02d}")
        body = f'''<div style="max-width:900px;margin:0 auto" class="anim-fade-up" data-anim="fade-up">
    <p class="kicker">{kicker}</p>
    <h1 class="h1 section-page-h">{title}</h1>
    <div class="divider-accent" style="margin:24px auto"></div>
  </div>
  <div class="deck-footer">
    <span class="dim2">Section {idx + 1}</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body, extra_class="section-page center")

    def _render_bullets(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """项目符号列表（左侧色条卡片）"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Key Points")
        lede_html = ""
        if page.text_blocks and page.text_blocks[0].is_lead:
            lede_html = f'<p class="lede mb-l">{self._esc(page.text_blocks[0].text)}</p>'
            items = page.text_blocks[1:]
        else:
            items = page.text_blocks

        items_html = ""
        for i, tb in enumerate(items[:8]):
            items_html += f'''<li class="anim-fade-left" data-anim="fade-left" style="animation-delay:{i * 80}ms">
        {self._emphasize(tb.text, tb.emphasis)}
      </li>'''

        body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  {lede_html}
  <ul class="bullet-list anim-stagger-list mt-l" data-anim-target>
    {items_html}
  </ul>
  <div class="deck-footer">
    <span class="dim2">{self._esc(page.kicker or "要点")}</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_kpi_grid(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """KPI 卡片网格（4 列）"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Metrics")
        cards = ""
        for i, m in enumerate(page.kpi_metrics[:8]):
            value = self._esc(str(m.get("value", "")))
            label = self._esc(m.get("label", ""))
            change = m.get("change", "")
            change_class = "good" if m.get("trend") == "up" else ("bad" if m.get("trend") == "down" else "")
            change_html = f'<p class="dim" style="color:var(--{change_class or "text-2"})">{self._esc(change)}</p>' if change else ""

            cards += f'''<div class="card anim-rise-in" data-anim="rise-in" style="animation-delay:{i * 100}ms">
        <p class="eyebrow">{label}</p>
        <div style="font-size:56px;font-weight:800;line-height:1;margin-top:8px"><span class="counter" data-to="{self._esc(str(m.get("raw_value", value)))}">0</span></div>
        {change_html}
      </div>'''

        body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="grid g4 mt-l anim-stagger-list" data-anim-target>
    {cards}
  </div>
  <div class="deck-footer">
    <span class="dim2">关键指标</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_two_column(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """双栏布局"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Pattern")
        left = ""
        right = ""
        items = page.text_blocks[:6]
        for i, tb in enumerate(items):
            target = left if i % 2 == 0 else right
            target += f'''<div class="card anim-fade-left" data-anim="fade-left" style="animation-delay:{i * 80}ms">
        <h4>{self._emphasize(tb.text, tb.emphasis)}</h4>
      </div>'''

        body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="grid g2 mt-l" style="align-items:start">
    <div class="stack">{left}</div>
    <div class="stack">{right}</div>
  </div>
  <div class="deck-footer">
    <span class="dim2">对比</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_three_column(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """三列布局"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Pillars")
        cards = ""
        for i, tb in enumerate(page.text_blocks[:6]):
            cards += f'''<div class="card anim-rise-in" data-anim="rise-in" style="animation-delay:{i * 100}ms">
        <h4>{self._emphasize(tb.text, tb.emphasis)}</h4>
      </div>'''

        body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="grid g3 mt-l anim-stagger-list" data-anim-target>
    {cards}
  </div>
  <div class="deck-footer">
    <span class="dim2">三栏</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_table(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """数据表格"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Data")
        if not page.table_data:
            return self._render_content(page, idx, total)

        headers = page.table_data.get("headers", [])
        rows = page.table_data.get("rows", [])

        ths = "".join(f"<th>{self._esc(h)}</th>" for h in headers)
        trs = ""
        for row in rows[:10]:
            tds = ""
            for i, cell in enumerate(row):
                cell_str = self._esc(str(cell))
                # 检测数字/涨跌
                cls = ""
                if isinstance(cell, (int, float)):
                    cls = ' class="num"'
                elif isinstance(cell, str):
                    if cell.startswith("+") or "↑" in cell:
                        cls = ' class="up"'
                    elif cell.startswith("-") or "↓" in cell:
                        cls = ' class="dn"'
                    elif i > 0 and any(c.isdigit() for c in cell) and i == len(row) - 1:
                        cls = ' class="num"'
                tds += f"<td{cls}>{cell_str}</td>"
            trs += f"<tr>{tds}</tr>"

        body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="tbl-wrap mt-l anim-fade-up" data-anim="fade-up">
    <table class="tbl">
      <thead><tr>{ths}</tr></thead>
      <tbody>{trs}</tbody>
    </table>
  </div>
  <div class="deck-footer">
    <span class="dim2">数据表</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_image_hero(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """大图背景 + 文字覆盖"""
        if not page.image_blocks:
            return self._render_content(page, idx, total)
        img = page.image_blocks[0]
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Visualization")
        body = f'''<div class="image-card anim-fade-up" data-anim="fade-up">
    <img src="{self._esc(img.url)}" alt="{self._esc(img.caption)}" style="height:480px;object-fit:contain;padding:32px">
    <div class="caption" style="padding:20px 28px">
      <h3 class="mt-0">{title}</h3>
      <p class="dim mt-0">{self._esc(img.caption)}</p>
    </div>
  </div>
  <div class="deck-footer">
    <span class="dim2">{kicker}</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_image_grid(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """图片网格"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Gallery")
        cards = ""
        for i, img in enumerate(page.image_blocks[:6]):
            cards += f'''<div class="image-card anim-rise-in" data-anim="rise-in" style="animation-delay:{i * 80}ms">
        <img src="{self._esc(img.url)}" alt="{self._esc(img.caption)}">
        <div class="caption">{self._esc(img.caption)}</div>
      </div>'''

        body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="grid g3 mt-l anim-stagger-list" data-anim-target>
    {cards}
  </div>
  <div class="deck-footer">
    <span class="dim2">图集</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body)

    def _render_stat(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """大数字突出页"""
        if not page.kpi_metrics:
            return self._render_content(page, idx, total)
        m = page.kpi_metrics[0]
        value = self._esc(str(m.get("value", "0")))
        raw = m.get("raw_value", value)
        unit = self._esc(m.get("unit", ""))
        label = self._esc(m.get("label", page.title))
        kicker = self._esc(page.kicker or "Impact")
        body = f'''<p class="kicker">{kicker}</p>
  <div style="font-size:200px;line-height:1;font-weight:900;letter-spacing:-.04em">
    <span class="counter gradient-text" data-to="{self._esc(str(raw))}">0</span><span class="gradient-text">{unit}</span>
  </div>
  <h2 class="h2 mt-l">{label}</h2>
  <p class="lede">{self._esc(page.text_blocks[0].text if page.text_blocks else page.title)}</p>
  <div class="deck-footer">
    <span class="dim2">关键数字</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body, extra_class="center tc")

    def _render_thanks(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """结尾致谢页"""
        title = self._esc(page.title or "Thanks")
        body = f'''<h1 class="h1 anim-fade-up" data-anim="fade-up" style="font-size:160px;line-height:1">
    <span class="gradient-text">{title}</span>
  </h1>
  <p class="lede mt-l">{self._esc(page.text_blocks[0].text if page.text_blocks else "")}</p>
  <div class="row mt-l" style="justify-content:center;gap:32px">
    <span class="dim2">报告生成于 {idx + 1}/{total}</span>
  </div>
  <div class="deck-footer">
    <span class="dim2">致谢</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        return self._wrap_slide(page, idx, total, body, extra_class="center tc")

    def _render_content(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """通用内容页：左文 + 右图 或 上文 + 下图"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Analysis")

        # 文本
        paragraphs = []
        for tb in page.text_blocks[:6]:
            cls = "lede" if tb.is_lead else ""
            paragraphs.append(f'<p class="{cls}">{self._emphasize(tb.text, tb.emphasis)}</p>')
        text_html = "\n      ".join(paragraphs) if paragraphs else ""

        # 图片
        image_html = ""
        if page.image_blocks:
            img = page.image_blocks[0]
            image_html = f'''<div class="image-card anim-fade-right" data-anim="fade-right">
        <img src="{self._esc(img.url)}" alt="{self._esc(img.caption)}">
        <div class="caption">{self._esc(img.caption)}</div>
      </div>'''

        # 表格
        table_html = ""
        if page.table_data:
            headers = page.table_data.get("headers", [])
            rows = page.table_data.get("rows", [])[:6]
            ths = "".join(f"<th>{self._esc(h)}</th>" for h in headers)
            trs = "".join(
                "<tr>" + "".join(f"<td>{self._esc(str(c))}</td>" for c in row) + "</tr>"
                for row in rows
            )
            table_html = f'''<div class="tbl-wrap anim-fade-up mt-m" data-anim="fade-up">
        <table class="tbl">
          <thead><tr>{ths}</tr></thead>
          <tbody>{trs}</tbody>
        </table>
      </div>'''

        if image_html and text_html:
            # 左文右图
            body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="grid g2 mt-l" style="align-items:start">
    <div class="stack anim-fade-left" data-anim="fade-left">
      {text_html}
    </div>
    <div class="stack">
      {image_html}
    </div>
  </div>
  {table_html}
  <div class="deck-footer">
    <span class="dim2">分析</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        elif text_html and table_html:
            # 上文 + 表
            body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="stack anim-fade-up" data-anim="fade-up" style="max-width:none">
    {text_html}
  </div>
  {table_html}
  <div class="deck-footer">
    <span class="dim2">分析</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        elif image_html and not text_html:
            # 大图为主
            body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  {image_html}
  <div class="deck-footer">
    <span class="dim2">可视化</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''
        else:
            # 纯文本
            body = f'''<p class="kicker">{kicker}</p>
  <h2 class="h2">{title}</h2>
  <div class="stack anim-fade-up" data-anim="fade-up" style="max-width:none">
    {text_html}
  </div>
  {table_html}
  <div class="deck-footer">
    <span class="dim2">分析</span>
    <span class="slide-number" data-current="{idx + 1}" data-total="{total}"></span>
  </div>'''

        return self._wrap_slide(page, idx, total, body)

    def _render_chart_page(self, page: HTMLPageModel, idx: int, total: int) -> str:
        """Chart.js 图表页（柱状图 / 折线图 / 饼图）"""
        title = self._esc(page.title)
        kicker = self._esc(page.kicker or "Chart")

        if not page.chart_data:
            return self._render_content(page, idx, total)

        chart_type_map = {
            LayoutType.CHART_BAR: "bar",
            LayoutType.CHART_LINE: "line",
            LayoutType.CHART_PIE: "pie",
        }
        chart_type = chart_type_map.get(page.layout, "bar")

        labels = page.chart_data.get("labels", [])
        datasets_cfg = page.chart_data.get("datasets", [])
        labels_js = ",".join("'" + self._esc(str(l)) + "'" for l in labels)

        datasets_js_parts = []
        for ds in datasets_cfg:
            data_str = ",".join(str(v) for v in ds.get("data", []))
            label_esc = self._esc(ds.get("label", ""))
            if chart_type == "pie":
                datasets_js_parts.append(
                    "{data:[" + data_str + "],backgroundColor:accent}"
                )
            else:
                datasets_js_parts.append(
                    "{label:'" + label_esc + "',data:[" + data_str + "],backgroundColor:accent,borderRadius:6}"
                )
        datasets_js = ",".join(datasets_js_parts)

        if chart_type == "pie":
            options_js = "{plugins:{legend:{labels:{color:text2}}}}"
        else:
            options_js = (
                "{plugins:{legend:{labels:{color:text2}}}"
                ",scales:{x:{ticks:{color:text2},grid:{color:border}}"
                ",y:{ticks:{color:text2},grid:{color:border}}}}"
            )

        chart_id = "chart_" + str(idx)

        chart_script = (
            "addEventListener('DOMContentLoaded',()=>{"
            "const css=getComputedStyle(document.documentElement);"
            "const accent=css.getPropertyValue('--accent').trim();"
            "const text2=css.getPropertyValue('--text-2').trim();"
            "const border=css.getPropertyValue('--border').trim();"
            "new Chart(document.getElementById('" + chart_id + "'),{type:'" + chart_type + "',"
            "data:{labels:[" + labels_js + "],"
            "datasets:[" + datasets_js + "]},"
            "options:" + options_js + "});"
            "});"
        )

        body = (
            '<p class="kicker">' + kicker + '</p>\n'
            '  <h2 class="h2">' + title + '</h2>\n'
            '  <div class="card mt-l" style="height:520px;padding:28px">\n'
            '    <canvas id="' + chart_id + '"></canvas>\n'
            '  </div>\n'
            '  <script>\n'
            '    ' + chart_script + '\n'
            '  </script>\n'
            '  <div class="deck-footer">\n'
            '    <span class="dim2">' + kicker + '</span>\n'
            '    <span class="slide-number" data-current="' + str(idx + 1) + '" data-total="' + str(total) + '"></span>\n'
            '  </div>'
        )
        return self._wrap_slide(page, idx, total, body)


# ============================================================
# 便捷函数
# ============================================================

def quick_generate(
    title: str,
    sections: List[Dict[str, Any]],
    theme: str = "minimal-white",
) -> str:
    """快速生成报告 HTML

    Args:
        title: 报告标题
        sections: 章节列表，每项为 {"title": str, "content": str, "images": [...], "table": {...}}
        theme: 主题名
    """
    pages: List[HTMLPageModel] = []
    # 封面
    pages.append(HTMLPageModel(
        title=title,
        layout=LayoutType.COVER,
        kicker="研究报告",
        text_blocks=[HTMLTextBlock(text=sections[0]["content"][:200] if sections else "")] if sections else [],
    ))
    # 目录
    pages.append(HTMLPageModel(
        title="目录",
        layout=LayoutType.TOC,
        kicker="Contents",
        text_blocks=[HTMLTextBlock(text=s.get("title", "")) for s in sections],
    ))
    # 章节
    for sec in sections:
        pages.append(HTMLPageModel(
            title=sec.get("title", ""),
            layout=LayoutType.CONTENT,
            text_blocks=[HTMLTextBlock(text=sec.get("content", ""))],
            image_blocks=[HTMLImageBlock(url=img) for img in sec.get("images", [])],
            table_data=sec.get("table"),
        ))

    return HTMLReportGenerator(theme=theme).generate(pages)
