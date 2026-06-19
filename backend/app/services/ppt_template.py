"""
PPT 母版模板加载与填充服务

核心职责：
1. 扫描 `backend/app/templates/ppt/` 目录下的 .pptx 母版
2. 解析每个母版的 slide_master 与 slide_layouts
3. 提供 list_templates() / get_template() / fill_template() 三个对外接口
4. 内部缓存已加载的模板对象，避免每次导出重新解析

设计原则：
- 模板 ID 来自 MANIFEST.json，未配置时回退到文件名（template{N}）
- layout 选取策略：先按 layouts_hint 名称匹配，匹配不到时按布局功能（cover/section/content/picture/summary）选最接近的
- 所有数据填充通过 add_slide(layout) + placeholder.text_frame 操作，不破坏母版的背景/字体/配色
- 长内容自动分页；配图按比例缩放
"""

import io
import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from pptx import Presentation
from pptx.util import Emu, Inches, Pt
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor

from app.models.report import Report

logger = logging.getLogger(__name__)

# 模板根目录（可被环境变量覆盖，便于测试）
TEMPLATES_DIR = os.environ.get(
    "PPT_TEMPLATES_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "ppt"),
)

# 单幻灯片正文承载上限（字符），超过则自动分页
MAX_CHARS_PER_CONTENT_SLIDE = 300


def _make_unique(name: str, suffix: int) -> str:
    """生成唯一的 zip entry 名称：name -> name_dup{suffix}"""
    if "." in name:
        base, ext = name.rsplit(".", 1)
        return f"{base}_dup{suffix}.{ext}"
    return f"{name}_dup{suffix}"


# ─────────────────────────── 数据结构 ───────────────────────────


@dataclass
class TemplateInfo:
    """模板元数据（API 返回）"""
    id: str
    name: str
    description: str
    file: str
    layouts_count: int = 0


@dataclass
class TemplateContext:
    """已加载的模板对象（包含 Presentation 实例和解析后的 layout 映射）"""
    info: TemplateInfo
    file_path: str
    presentation: Presentation
    cover_layouts: List[Any] = field(default_factory=list)      # 封面
    section_layouts: List[Any] = field(default_factory=list)    # 章节封面
    content_layouts: List[Any] = field(default_factory=list)    # 正文
    picture_layouts: List[Any] = field(default_factory=list)    # 配图
    summary_layouts: List[Any] = field(default_factory=list)    # 总结

    def pick_cover(self, idx: int = 0):
        return self.cover_layouts[idx] if self.cover_layouts else (
            self.section_layouts[0] if self.section_layouts else
            (self.content_layouts[0] if self.content_layouts else self.presentation.slide_layouts[0])
        )

    def pick_section(self, idx: int = 0):
        return self.section_layouts[idx % len(self.section_layouts)] if self.section_layouts else self.pick_cover()

    def pick_content(self, idx: int = 0):
        return self.content_layouts[idx % len(self.content_layouts)] if self.content_layouts else self.pick_cover()

    def pick_picture(self, idx: int = 0):
        return self.picture_layouts[idx % len(self.picture_layouts)] if self.picture_layouts else self.pick_content()

    def pick_summary(self, idx: int = 0):
        return self.summary_layouts[idx % len(self.summary_layouts)] if self.summary_layouts else self.pick_section()


# ─────────────────────────── 模板服务 ───────────────────────────


class PPTTemplateService:
    """PPT 母版模板加载与填充服务（单例）"""

    _instance: Optional["PPTTemplateService"] = None
    _templates: Dict[str, TemplateContext] = {}
    _manifest: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── 公开 API ─────────────────────────────────────────────

    def list_templates(self) -> List[TemplateInfo]:
        """返回所有已加载模板的元数据列表（供前端拉取）"""
        self._ensure_loaded()
        return [ctx.info for ctx in self._templates.values()]

    def get_template(self, template_id: str) -> Optional[TemplateContext]:
        """按 ID 返回缓存的模板上下文，找不到时返回 None"""
        self._ensure_loaded()
        return self._templates.get(template_id)

    def fill_template(
        self,
        template_id: str,
        report: Report,
        chart_images: Optional[List[Dict[str, str]]] = None,
    ) -> bytes:
        """核心入口：用指定模板生成填充后的 PPTX 字节流"""
        self._ensure_loaded()
        ctx = self._templates.get(template_id)
        if not ctx:
            logger.warning("Template '%s' not found, falling back to first available", template_id)
            ctx = next(iter(self._templates.values()), None)
        if not ctx:
            # 无任何模板可用，回退到内置默认（与旧 generate_pptx 行为一致）
            return self._fallback_pptx(report, chart_images)

        # 每次生成都从模板文件重新加载 Presentation,确保干净状态
        prs = Presentation(ctx.file_path)

        # ── 关键步骤: 清空模板原 slide,只保留 slide_masters / slide_layouts ──
        # 原因:模板是用户手工制作的"设计母版",里面通常有 5 张示例 slide。
        # 如果不清空,新追加的报告 slide 会接在示例 slide 后面,PowerPoint
        # 默认从第 1 张展示,导致用户看到模板原内容("月度市场动态(国内)")
        # 而不是报告内容。
        try:
            original_slide_count = len(prs.slides)
            xml_slides = prs.slides._sldIdLst
            # 必须先复制成 list 再 remove,否则会边遍历边修改
            slides_to_remove = list(xml_slides)
            for slide_id in slides_to_remove:
                xml_slides.remove(slide_id)
            logger.info(
                "[PPT-TEMPLATE] Cleared %d original slides from template '%s', "
                "keeping only slide_masters/slide_layouts for design consistency",
                original_slide_count, template_id,
            )
        except Exception as clear_e:
            logger.warning(
                "[PPT-TEMPLATE] Failed to clear original slides from template '%s': "
                "%s. Generated PPT may contain template example slides.",
                template_id, clear_e, exc_info=True,
            )

        # 1. 解析报告 Markdown 为结构化大纲
        outline = self._parse_outline(report)

        # 2. 封面 slide
        self._add_cover_slide(prs, ctx, report)

        # 3. 目录 slide（自动列出所有 ## 章节）
        section_titles = [s["title"] for s in outline["sections"]]
        if section_titles:
            self._add_toc_slide(prs, ctx, report.title, section_titles)

        # 4. 每个章节：章节封面 + 正文（自动分页）
        for sec_idx, section in enumerate(outline["sections"], start=1):
            # 4.1 章节封面
            self._add_section_cover_slide(prs, ctx, sec_idx, section)

            # 4.2 正文（按 MAX_CHARS_PER_CONTENT_SLIDE 自动分页）
            for page_idx, chunk in enumerate(self._split_section_content(section["content"])):
                self._add_content_slide(prs, ctx, section["title"], chunk, page_idx=page_idx)

            # 4.3 该章节末尾插入配图（按 position 匹配）
            sec_charts = [c for c in (chart_images or []) if c.get("position") == sec_idx]
            for ci in sec_charts:
                self._add_picture_slide(prs, ctx, ci)

        # 5. 总结 slide
        self._add_summary_slide(prs, ctx, report, outline["sections"])

        # 6. 序列化
        buf = io.BytesIO()
        prs.save(buf)
        raw = buf.getvalue()
        # 7. 后处理：去重 zip 内部重名 part（用户原始模板的多 master 结构会触发此问题）
        return self._dedupe_zip_parts(raw)

    # ── 内部：加载与解析 ─────────────────────────────────────

    def _ensure_loaded(self):
        """确保模板已扫描并缓存（首次访问时执行）"""
        if self._templates:
            return
        self._load_manifest()
        self._scan_templates()

    def _load_manifest(self):
        manifest_path = os.path.join(TEMPLATES_DIR, "MANIFEST.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    self._manifest = json.load(f)
            except Exception as e:
                logger.warning("Failed to load MANIFEST.json: %s, falling back to file-based discovery", e)
                self._manifest = {}
        else:
            self._manifest = {}

    def _scan_templates(self):
        """扫描目录，加载所有 .pptx 母版并按名称归类 layout"""
        if not os.path.isdir(TEMPLATES_DIR):
            logger.warning("PPT templates dir does not exist: %s", TEMPLATES_DIR)
            return

        manifest_templates = {t["id"]: t for t in self._manifest.get("templates", [])}
        # 用绝对路径作为去重 key（同一个文件不应被加载两次）
        registered_files: set = set()

        # 先按 MANIFEST 顺序加载
        for tid, meta in manifest_templates.items():
            file_path = os.path.abspath(os.path.join(TEMPLATES_DIR, meta["file"]))
            if os.path.exists(file_path):
                self._register_template(tid, meta, file_path)
                registered_files.add(file_path)

        # 再扫描目录中未在 MANIFEST 里的 .pptx
        for fname in sorted(os.listdir(TEMPLATES_DIR)):
            if not fname.lower().endswith(".pptx"):
                continue
            file_path = os.path.abspath(os.path.join(TEMPLATES_DIR, fname))
            if file_path in registered_files:
                continue
            stem = os.path.splitext(fname)[0]
            tid = stem  # template1/template2/template3
            self._register_template(
                tid,
                {
                    "id": tid,
                    "file": fname,
                    "name": stem,
                    "description": "未在 MANIFEST 中注册的模板",
                    "layouts_hint": {},
                },
                file_path,
            )
            registered_files.add(file_path)

        logger.info("PPTTemplateService: loaded %d template(s)", len(self._templates))

    def _register_template(self, tid: str, meta: Dict[str, Any], file_path: str):
        # 优先加载去重后的副本（源文件若有重复 slide layout 名，python-pptx 保存时 zipfile 会冲突）
        usable_path = self._sanitize_template(file_path)
        try:
            prs = Presentation(usable_path)
        except Exception as e:
            logger.error("Failed to open template %s: %s", usable_path, e)
            return

        ctx = TemplateContext(
            info=TemplateInfo(
                id=meta["id"],
                name=meta.get("name", tid),
                description=meta.get("description", ""),
                file=meta.get("file", os.path.basename(file_path)),
            ),
            file_path=usable_path,
            presentation=prs,
        )
        ctx.info.layouts_count = sum(len(m.slide_layouts) for m in prs.slide_masters)

        # 按 layouts_hint 归类 layouts
        hints = meta.get("layouts_hint", {})
        ctx.cover_layouts = self._resolve_layouts(prs, hints.get("cover", []))
        ctx.section_layouts = self._resolve_layouts(prs, hints.get("section", []))
        ctx.content_layouts = self._resolve_layouts(prs, hints.get("content", []))
        ctx.picture_layouts = self._resolve_layouts(
            prs, hints.get("picture") or hints.get("content", [])
        )
        ctx.summary_layouts = self._resolve_layouts(
            prs, hints.get("summary") or hints.get("section", [])
        )

        self._templates[tid] = ctx
        logger.info(
            "Loaded template '%s' from %s (cover=%d, section=%d, content=%d)",
            tid, usable_path,
            len(ctx.cover_layouts), len(ctx.section_layouts), len(ctx.content_layouts),
        )

    def _sanitize_template(self, file_path: str) -> str:
        """检测并修复源模板中的重复 slide layout / master 名字。

        问题背景：用户手工制作的 .pptx 在某些 PowerPoint 版本下允许同 master 下
        存在重名 layout（保存时不强制唯一），但 python-pptx 重新写入时会因
        zipfile 内部文件冲突产生警告并可能生成不合法 pptx。

        解决：首次加载时把模板去重后写入 cache 子目录，后续直接用 cache 版本。
        """
        cache_dir = os.path.join(TEMPLATES_DIR, "cache")
        # 缓存文件路径（按源文件 mtime 生成版本号，避免热更新失效）
        try:
            mtime = int(os.path.getmtime(file_path))
        except OSError:
            mtime = 0
        cached = os.path.join(cache_dir, f"{os.path.basename(file_path)}.{mtime}.clean.pptx")

        if os.path.exists(cached):
            return cached

        try:
            src_prs = Presentation(file_path)
        except Exception as e:
            logger.warning("_sanitize_template: cannot read %s: %s", file_path, e)
            return file_path

        # 检测重复：把所有 layout name 收集，统计重复
        seen_names: Dict[str, int] = {}
        for master in src_prs.slide_masters:
            for lay in master.slide_layouts:
                nm = lay.name or ""
                seen_names[nm] = seen_names.get(nm, 0) + 1
        has_dup_layout = any(c > 1 for c in seen_names.values())

        # master 重名
        seen_masters: Dict[str, int] = {}
        for master in src_prs.slide_masters:
            nm = master.name or f"master_{id(master)}"
            seen_masters[nm] = seen_masters.get(nm, 0) + 1
        has_dup_master = any(c > 1 for c in seen_masters.values())

        if not has_dup_layout and not has_dup_master:
            return file_path

        # 有重复：通过修改 partname 让它们在 OOXML 中唯一
        # 实际上 layout.name 只是显示名，不影响 partname。但部分 PowerPoint 工具
        # 会用 name 生成 partname，导致 zipfile 冲突。我们直接重命名重复 layout。
        for mi, master in enumerate(src_prs.slide_masters):
            used = set()
            for li, lay in enumerate(master.slide_layouts):
                base = lay.name or f"Layout{li}"
                new_name = base
                suffix = 2
                while new_name in used:
                    new_name = f"{base} ({suffix})"
                    suffix += 1
                used.add(new_name)
                if new_name != lay.name:
                    try:
                        lay.name = new_name
                    except Exception:
                        pass

        # master 同样处理
        used_m = set()
        for mi, master in enumerate(src_prs.slide_masters):
            base = master.name or f"Master{mi}"
            new_name = base
            suffix = 2
            while new_name in used_m:
                new_name = f"{base} ({suffix})"
                suffix += 1
            used_m.add(new_name)
            if new_name != master.name:
                try:
                    master.name = new_name
                except Exception:
                    pass

        os.makedirs(cache_dir, exist_ok=True)
        try:
            src_prs.save(cached)
            logger.info("_sanitize_template: sanitized %s -> %s", file_path, cached)
            return cached
        except Exception as e:
            logger.warning("_sanitize_template: save sanitized copy failed: %s; using original", e)
            return file_path

    def _resolve_layouts(self, prs: Presentation, names: List[str]) -> List[Any]:
        """按名称列表从所有 master 的 layouts 中匹配"""
        if not names:
            return []
        result = []
        all_layouts = []
        for m in prs.slide_masters:
            for lay in m.slide_layouts:
                all_layouts.append(lay)
        for name in names:
            for lay in all_layouts:
                if lay.name == name and lay not in result:
                    result.append(lay)
                    break
        return result

    # ── 内部：报告解析 ───────────────────────────────────────

    def _parse_outline(self, report: Report) -> Dict[str, Any]:
        """把报告 Markdown 拆为：标题 + 章节列表(每章节含 title/content/level)"""
        content = report.content_markdown or ""
        lines = content.split("\n")

        title = report.title
        sections: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for raw in lines:
            line = raw.rstrip()
            if line.startswith("## "):
                # 切到下一章节
                if current is not None:
                    current["content"] = current["content"].strip()
                    sections.append(current)
                current = {"title": line[3:].strip(), "content": "", "level": 2}
            elif line.startswith("# ") and not sections and current is None:
                title = line[2:].strip()
            else:
                if current is None:
                    # ## 出现之前的内容，丢掉
                    continue
                current["content"] += line + "\n"

        if current is not None:
            current["content"] = current["content"].strip()
            sections.append(current)

        return {"title": title, "sections": sections}

    def _split_section_content(self, text: str) -> List[str]:
        """把长正文拆成多块，每块不超过 MAX_CHARS_PER_CONTENT_SLIDE 字符"""
        text = (text or "").strip()
        if not text:
            return [""]
        if len(text) <= MAX_CHARS_PER_CONTENT_SLIDE:
            return [text]

        chunks: List[str] = []
        remaining = text
        while len(remaining) > MAX_CHARS_PER_CONTENT_SLIDE:
            window = remaining[:MAX_CHARS_PER_CONTENT_SLIDE * 2]  # 截取略多以便寻找断点
            # 优先按句号/换行符分割
            cut = -1
            for sep in ["。\n", "。", "\n\n", "\n", "；", "，", " "]:
                pos = window.rfind(sep, 0, MAX_CHARS_PER_CONTENT_SLIDE)
                if pos > cut:
                    cut = pos + len(sep)
            if cut <= 0:
                cut = MAX_CHARS_PER_CONTENT_SLIDE
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    # ── 内部：占位符填充 ─────────────────────────────────────

    def _set_placeholder_text(self, slide, idx_predicate, text: str, font_size: Optional[int] = None, bold: Optional[bool] = None):
        """找到第一个满足 idx_predicate(idx, type, name) 的占位符并填充文本"""
        for ph in slide.placeholders:
            if idx_predicate(ph.placeholder_format.idx, ph.placeholder_format.type, ph.name):
                tf = ph.text_frame
                tf.clear()
                p = tf.paragraphs[0]
                run = p.add_run()
                run.text = text
                if font_size is not None:
                    run.font.size = Pt(font_size)
                if bold is not None:
                    run.font.bold = bold
                return True
        return False

    def _add_cover_slide(self, prs: Presentation, ctx: TemplateContext, report: Report):
        layout = ctx.pick_cover(0)
        slide = prs.slides.add_slide(layout)
        # 标题占位符
        self._set_placeholder_text(
            slide,
            lambda i, t, n: t in (1, 3) or "标题" in n,
            report.title or "",
            font_size=32,
            bold=True,
        )
        # 副标题占位符
        subtitle = report.summary or datetime.now().strftime("%Y.%m")
        self._set_placeholder_text(
            slide,
            lambda i, t, n: t == 4 or "副标题" in n,
            subtitle,
            font_size=16,
        )

    def _add_toc_slide(self, prs: Presentation, ctx: TemplateContext, title: str, items: List[str]):
        layout = ctx.pick_content(0) if ctx.content_layouts else ctx.pick_cover(0)
        slide = prs.slides.add_slide(layout)
        # 标题
        self._set_placeholder_text(
            slide,
            lambda i, t, n: t in (1, 3) or "标题" in n,
            "目录",
            font_size=28,
            bold=True,
        )
        # 正文（找一个 BODY/OBJECT 占位符）
        body_filled = False
        for ph in slide.placeholders:
            if ph.placeholder_format.type in (2, 7):  # BODY or OBJECT
                tf = ph.text_frame
                tf.clear()
                for i, item in enumerate(items, start=1):
                    p = tf.add_paragraph() if i > 1 else tf.paragraphs[0]
                    p.text = f"{i:02d}. {item}"
                    p.level = 0
                body_filled = True
                break
        if not body_filled:
            # 没有 body 占位符就自己加一个 textbox
            tx = slide.shapes.add_textbox(Inches(0.8), Inches(2.0), Inches(11.0), Inches(5.0))
            tf = tx.text_frame
            tf.word_wrap = True
            for i, item in enumerate(items, start=1):
                p = tf.paragraphs[0] if i == 1 else tf.add_paragraph()
                p.text = f"{i:02d}. {item}"
                p.font.size = Pt(18)

    def _add_section_cover_slide(self, prs: Presentation, ctx: TemplateContext, idx: int, section: Dict[str, Any]):
        layout = ctx.pick_section(idx - 1)
        slide = prs.slides.add_slide(layout)
        # 章节号
        self._set_placeholder_text(
            slide,
            lambda i, t, n: "占位符" in n and i != 0 and t in (1, 3),
            f"{idx:02d}",
            font_size=44,
            bold=True,
        ) or self._set_placeholder_text(
            slide,
            lambda i, t, n: True,
            f"{idx:02d}  {section['title']}",
            font_size=24,
            bold=True,
        )

    def _add_content_slide(self, prs: Presentation, ctx: TemplateContext, section_title: str, content: str, page_idx: int = 0):
        layout = ctx.pick_content(page_idx)
        slide = prs.slides.add_slide(layout)
        # 标题
        title_text = section_title if page_idx == 0 else f"{section_title} (续)"
        self._set_placeholder_text(
            slide,
            lambda i, t, n: t in (1, 3) or "标题" in n,
            title_text,
            font_size=22,
            bold=True,
        )
        # 正文
        body_filled = False
        for ph in slide.placeholders:
            if ph.placeholder_format.type in (2, 7):
                tf = ph.text_frame
                tf.clear()
                self._fill_text_frame(tf, content)
                body_filled = True
                break
        if not body_filled:
            tx = slide.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.0), Inches(5.5))
            tf = tx.text_frame
            tf.word_wrap = True
            self._fill_text_frame(tf, content)

    def _fill_text_frame(self, tf, content: str):
        """把 Markdown 段落塞到 text_frame 中，每段一个 paragraph"""
        paragraphs = [p.strip() for p in re.split(r"\n+", content) if p.strip()]
        if not paragraphs:
            paragraphs = [""]
        for i, p_text in enumerate(paragraphs):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            # 处理 ### 三级标题
            if p_text.startswith("### "):
                p.text = p_text[4:]
                p.font.bold = True
                p.font.size = Pt(16)
            elif p_text.startswith("- ") or p_text.startswith("* "):
                p.text = "• " + p_text[2:]
                p.font.size = Pt(14)
            else:
                p.text = p_text
                p.font.size = Pt(14)
            p.space_after = Pt(6)

    def _add_picture_slide(self, prs: Presentation, ctx: TemplateContext, chart: Dict[str, str]):
        layout = ctx.pick_picture(0)
        slide = prs.slides.add_slide(layout)
        title = chart.get("title", "图表")
        # 标题
        self._set_placeholder_text(
            slide,
            lambda i, t, n: t in (1, 3) or "标题" in n,
            title,
            font_size=20,
            bold=True,
        )
        # 图片占位符优先，否则直接 add_picture
        pic_added = False
        for ph in slide.placeholders:
            if ph.placeholder_format.type == 18:  # PICTURE
                try:
                    img_blob = io.BytesIO(base64.b64decode(chart["base64"]))
                    ph.insert_picture(img_blob)
                    pic_added = True
                except Exception as e:
                    logger.warning("insert_picture into placeholder failed: %s", e)
                break
        if not pic_added:
            try:
                img_blob = io.BytesIO(base64.b64decode(chart["base64"]))
                # 缩放至画布 85% 宽，居中
                slide_w = prs.slide_width
                slide_h = prs.slide_height
                max_w = int(slide_w * 0.85)
                max_h = int(slide_h * 0.65)
                from PIL import Image as PILImage
                try:
                    pil = PILImage.open(img_blob)
                    iw, ih = pil.size
                    scale = min(max_w / iw, max_h / ih, 1.0)
                    pic = slide.shapes.add_picture(
                        img_blob,
                        int((slide_w - iw * scale) / 2),
                        Inches(1.5),
                        width=int(iw * scale),
                        height=int(ih * scale),
                    )
                except Exception:
                    # 装不了 PIL 时的兜底
                    slide.shapes.add_picture(img_blob, Inches(1), Inches(1.5), width=max_w)
            except Exception as e:
                logger.warning("Failed to add picture to slide: %s", e)

    def _add_summary_slide(self, prs: Presentation, ctx: TemplateContext, report: Report, sections: List[Dict[str, Any]]):
        layout = ctx.pick_summary(0)
        slide = prs.slides.add_slide(layout)
        self._set_placeholder_text(
            slide,
            lambda i, t, n: t in (1, 3) or "标题" in n,
            "总结与展望",
            font_size=28,
            bold=True,
        )
        # 总结正文：取最后一段 + 各章节标题
        last = sections[-1]["content"] if sections else (report.summary or "")
        body_filled = False
        for ph in slide.placeholders:
            if ph.placeholder_format.type in (2, 7):
                tf = ph.text_frame
                tf.clear()
                if last:
                    self._fill_text_frame(tf, last)
                else:
                    p = tf.paragraphs[0]
                    p.text = "本报告已完成全部维度的分析与总结"
                body_filled = True
                break
        if not body_filled:
            tx = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.0), Inches(5.5))
            tf = tx.text_frame
            tf.word_wrap = True
            if last:
                self._fill_text_frame(tf, last)

    # ── 内部：兜底 ───────────────────────────────────────────

    def _fallback_pptx(self, report: Report, chart_images: Optional[List[Dict[str, str]]] = None) -> bytes:
        """无任何模板可用时的最简版 PPT（与原 generate_pptx 行为一致）"""
        from pptx import Presentation as DefaultPresentation
        prs = DefaultPresentation()
        title_slide = prs.slides.add_slide(prs.slide_layouts[0])
        title_slide.shapes.title.text = report.title
        if len(title_slide.placeholders) > 1:
            title_slide.placeholders[1].text = report.summary or ""
        content_slide = prs.slides.add_slide(prs.slide_layouts[1])
        content_slide.shapes.title.text = "报告内容"
        body = content_slide.placeholders[1]
        tf = body.text_frame
        tf.clear()
        tf.text = (report.content_markdown or "")[:2000]
        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()

    # ── 内部：zip 去重 ───────────────────────────────────────

    def _dedupe_zip_parts(self, data: bytes) -> bytes:
        """修复 python-pptx 写出的 zip 内部重名 part。

        背景：用户提供的 .pptx 模板中多 master 场景下，python-pptx 重新打包时会
        出现多个相同 partname（如多个 slideLayout1.xml），导致 PowerPoint 打开
        时报"文件已损坏"。

        策略：按出现顺序给每个 entry 分配唯一名称，遇到重复时依次加 _dup1/_dup2/...
        并同步更新所有 .rels 中对旧 partname 的引用（含相对路径形式）。
        """
        import zipfile

        try:
            src_zip = zipfile.ZipFile(io.BytesIO(data), "r")
        except Exception:
            return data

        # 第一遍：按出现顺序去重
        names = src_zip.namelist()
        seen_count: Dict[str, int] = {}
        # key: 原 zip entry 在 names 列表中的索引；value: 最终写入的 entry 名
        index_to_name: Dict[int, str] = {}
        rename_map: Dict[str, str] = {}  # 原 partname -> 最终唯一名（最后一次出现的）

        for idx, n in enumerate(names):
            if n in seen_count:
                seen_count[n] += 1
                new_name = _make_unique(n, seen_count[n])
            else:
                seen_count[n] = 0
                new_name = n
            index_to_name[idx] = new_name
            # 记录"原 partname 最后一个被重命名后的名字"用于 .rels 替换
            if new_name != n:
                rename_map[n] = new_name

        if not rename_map:
            src_zip.close()
            return data

        # 第二遍：写新 zip
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst_zip:
            for idx, n in enumerate(names):
                content = src_zip.read(n)
                dst_zip.writestr(index_to_name[idx], content)

        # 第三遍：修复 .rels 文件中对旧 partname 的引用
        # 注意：rels 中 Target 是相对路径（如 slideLayouts/slideLayout1.xml），
        # 因此替换时要兼容"完整路径"和"裸文件名"两种形式。
        src_zip.close()
        out.seek(0)
        fixed = io.BytesIO()
        with zipfile.ZipFile(out, "r") as in_z, zipfile.ZipFile(fixed, "w", zipfile.ZIP_DEFLATED) as out_z:
            for item in in_z.infolist():
                content = in_z.read(item.filename)
                if item.filename.endswith(".rels"):
                    text = content.decode("utf-8", errors="ignore")
                    for old, new in rename_map.items():
                        # 完整路径形式
                        text = text.replace(f'"{old}"', f'"{new}"')
                        text = text.replace(f'/{old}"', f'/{new}"')
                        # 裸文件名形式（rels 中常省略父目录）
                        bare = old.rsplit("/", 1)[-1]
                        new_bare = new.rsplit("/", 1)[-1]
                        if bare != old:
                            text = text.replace(f'"{bare}"', f'"{new_bare}"')
                    content = text.encode("utf-8")
                out_z.writestr(item, content)

        return fixed.getvalue()
