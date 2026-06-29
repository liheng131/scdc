"""
ImageAssigner —— 图片-页面智能匹配分配器

对标豆包/千问的模板匹配机制：将 CollectorAgent 采集的截图
按内容相关性分配到 ReporterAgent 生成的各页面，实现图文结合。

核心逻辑：
1. 从每张图片的 source_url/title 提取关键词
2. 从每个页面的 title/kicker/content 提取关键词  
3. 计算 TF-IDF 风格的重叠得分，按得分降序分配到页面
4. 每页最多 2 张图片，多余图片分配到独立的 Image Grid 页
5. 无匹配的图片放入汇总图集页

数据流：
    CollectorAgent.extracted_images / user_uploaded_images
    → ImageAssigner.assign(pages, web_images, user_images)
    → {page_index: [HTMLImageBlock, ...], "overflow": [HTMLImageBlock, ...]}
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.html_report_generator import HTMLImageBlock, HTMLPageModel, LayoutType

logger = logging.getLogger(__name__)

# 中英文停用词（高频无效词，不参与关键词匹配）
_STOP_WORDS = {
    "的", "是", "在", "和", "了", "有", "不", "这", "也", "就", "都", "与", "及",
    "the", "is", "a", "an", "in", "on", "at", "to", "of", "and", "for", "or",
    "with", "from", "by", "as", "be", "it", "that", "this", "are", "was", "http",
    "https", "www", "com", "org", "net", "html", "htm", "php", "page", "index",
}


def _tokenize(text: str) -> List[str]:
    """中文按字拆分，英文按空格/标点拆分，去除停用词和短词"""
    if not text:
        return []
    # 提取中文字符和英文单词
    chinese = re.findall(r'[\u4e00-\u9fff]+', text)
    english = re.findall(r'[a-zA-Z]{3,}', text.lower())
    tokens = []
    for chunk in chinese:
        tokens.extend(list(chunk))
    tokens.extend(english)
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _keyword_score(page_tokens: List[str], image_tokens: List[str]) -> float:
    """计算页面和图片的 TF-IDF 风格重叠得分
    
    score = (共同 token 数)² / (页面 token 数 × 图片 token 数)
    等价于余弦相似度的简化版，避免长文本天然优势。
    """
    if not page_tokens or not image_tokens:
        return 0.0
    page_set = set(page_tokens)
    img_set = set(image_tokens)
    common = page_set & img_set
    if not common:
        return 0.0
    # Jaccard-like 得分，惩罚差异大的配对
    return len(common) / (len(page_set | img_set))


def _page_text(page: HTMLPageModel) -> str:
    """提取页面的全部文本用于关键词匹配"""
    parts = [page.title, page.kicker or ""]
    for tb in page.text_blocks:
        parts.append(tb.text)
    return " ".join(parts)


class ImageAssigner:
    """图片-页面智能匹配分配器"""

    def __init__(self, max_per_page: int = 3):  # 每页最多3张图片，提升图文丰富度
        self.max_per_page = max_per_page

    def assign(
        self,
        pages: List[HTMLPageModel],
        web_images: Optional[List[Dict[str, Any]]] = None,
        user_images: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[int, List[HTMLImageBlock]]:
        """将图片分配到最适合的页面

        Args:
            pages: HTML 页面模型列表
            web_images: 网页截图列表 [{"base64": str, "source_url": str, "title": str, "caption": str}, ...]
            user_images: 用户上传图片列表 [{"base64": str, "filename": str, ...}, ...]

        Returns:
            Dict[int, List[HTMLImageBlock]]: page_index → 分配到该页的图片列表
            - key=-1 → 多余的图片，应放入独立 Image Grid 页
        """
        all_images = self._merge_images(web_images, user_images)
        if not all_images:
            logger.info("ImageAssigner: no images to assign")
            return {}

        # 对主要内容页面（含 image/chart 类型）分配图片，提升图文覆盖率
        _ELIGIBLE_LAYOUTS = (
            LayoutType.CONTENT, LayoutType.BULLETS, LayoutType.KPI_GRID,
            LayoutType.TWO_COLUMN, LayoutType.THREE_COLUMN,
            LayoutType.IMAGE_HERO, LayoutType.IMAGE_GRID,
            LayoutType.STAT, LayoutType.TABLE,
        )
        content_pages = [
            (i, page) for i, page in enumerate(pages)
            if page.layout in _ELIGIBLE_LAYOUTS
        ]

        if not content_pages:
            logger.info("ImageAssigner: no content pages to assign images to")
            return {-1: all_images}

        # 预计算页面 token
        page_tokens_list = [(i, _tokenize(_page_text(page))) for i, page in content_pages]
        image_tokens_list = [
            (img, _tokenize(self._image_text(img))) for img in all_images
        ]

        # 计算每张图片与每个页面的匹配得分
        assignments: Dict[int, List[HTMLImageBlock]] = {i: [] for i, _ in content_pages}
        unassigned: List[HTMLImageBlock] = []

        for img, img_tokens in image_tokens_list:
            best_page_idx = -1
            best_score = 0.0
            for pi, pt in page_tokens_list:
                score = _keyword_score(pt, img_tokens)
                if score > best_score:
                    best_score = score
                    best_page_idx = pi

            img_block = self._to_image_block(img)
            if best_page_idx >= 0 and best_score > 0.02:  # 阈值:至少有一些重叠
                if len(assignments.get(best_page_idx, [])) < self.max_per_page:
                    assignments.setdefault(best_page_idx, []).append(img_block)
                    logger.debug(
                        "ImageAssigner: assigned img(%s) → page[%d](%s), score=%.3f",
                        img.get("source_url", img.get("filename", ""))[:50],
                        best_page_idx, pages[best_page_idx].title[:30], best_score,
                    )
                else:
                    unassigned.append(img_block)
            else:
                unassigned.append(img_block)

        # 未分配或溢出的图片 → key=-1
        if unassigned:
            assignments[-1] = unassigned
            logger.info(f"ImageAssigner: {len(unassigned)} images assigned to overflow grid")

        total_assigned = sum(len(v) for k, v in assignments.items() if k >= 0)
        logger.info(
            f"ImageAssigner: total={len(all_images)}, assigned={total_assigned}, "
            f"overflow={len(unassigned)}, pages_with_images={len([k for k, v in assignments.items() if k >= 0 and v])}"
        )
        return assignments

    def _merge_images(
        self,
        web_images: Optional[List[Dict[str, Any]]],
        user_images: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """合并 web_images 和 user_images 到统一格式"""
        merged = []
        for img in (web_images or []):
            merged.append({
                "base64": img.get("base64", ""),
                "source_url": img.get("source_url", img.get("url", "")),
                "title": img.get("title", ""),
                "caption": img.get("caption", img.get("title", "")),
                "type": "web_screenshot",
            })
        for img in (user_images or []):
            merged.append({
                "base64": img.get("base64", ""),
                "source_url": "",
                "title": img.get("filename", ""),
                "caption": img.get("caption", img.get("filename", "")),
                "type": "user_upload",
            })
        return merged

    def _image_text(self, img: Dict[str, Any]) -> str:
        """提取图片的描述文字用于关键词匹配"""
        return " ".join(filter(None, [
            img.get("title", ""),
            img.get("caption", ""),
            img.get("source_url", ""),
        ]))

    def _to_image_block(self, img: Dict[str, Any]) -> HTMLImageBlock:
        """将图片字典转为 HTMLImageBlock"""
        b64 = img.get("base64", "")
        url = f"data:image/png;base64,{b64}" if b64 and not b64.startswith("data:") else b64
        return HTMLImageBlock(
            url=url,
            caption=img.get("caption", img.get("title", "")),
            source=img.get("source_url", ""),
        )


# Module-level singleton
image_assigner = ImageAssigner()
