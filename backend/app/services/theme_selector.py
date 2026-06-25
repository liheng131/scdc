import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# Theme category definitions: each category maps to a list of candidate themes
# and associated keywords that trigger selection.
THEME_CATEGORIES = {
    "business_formal": {
        "themes": ["corporate-clean", "swiss-grid"],
        "keywords": [
            "董事会", "汇报", "B2B", "销售", "金融", "保险", "商务", "企业",
            "corporate", "business", "board", "meeting", "sales", "insurance",
            "战略", "管理", "咨询", "consulting", "strategy",
        ],
    },
    "tech_sharing": {
        "themes": ["tokyo-night", "dracula", "catppuccin-mocha", "nord"],
        "keywords": [
            "技术", "开发", "架构", "代码", "基础设施", "云", "DevOps",
            "tech", "development", "code", "infrastructure", "cloud",
            "分享", "talk", "conference", "编程", "API", "微服务",
            "后端", "前端", "全栈", "DevOps", "Kubernetes", "Docker",
        ],
    },
    "consumer_product": {
        "themes": ["xiaohongshu-white", "soft-pastel"],
        "keywords": [
            "产品", "发布", "消费者", "小红书", "生活", "美学", "品牌",
            "product", "launch", "consumer", "lifestyle", "aesthetic",
            "时尚", "潮流", "美妆", "护肤", "电商", "种草",
        ],
    },
    "financial_analysis": {
        "themes": ["corporate-clean", "arctic-cool"],
        "keywords": [
            "金融", "财务", "分析", "投资", "市场", "经济", "股票",
            "finance", "financial", "investment", "market", "economy",
            "报告", "报表", "审计", "风控", "理财", "基金",
        ],
    },
    "academic_report": {
        "themes": ["academic-paper", "minimal-white"],
        "keywords": [
            "学术", "论文", "研究", "实验", "学术报告", "分享会",
            "academic", "paper", "research", "study", "thesis",
            "科学", "文献", "期刊", "会议论文",
        ],
    },
}

DEFAULT_THEME = "minimal-white"


class ThemeSelector:
    """Selects an HTML-PPT CSS theme based on topic keywords and content."""

    def __init__(self):
        self._categories = THEME_CATEGORIES
        self._default_theme = DEFAULT_THEME

    def _normalize(self, text: str) -> str:
        """Lowercase and strip for matching."""
        return text.lower().strip()

    def _count_matches(self, text: str, keywords: List[str]) -> int:
        """Count how many keywords appear in the text (case-insensitive)."""
        text_lower = self._normalize(text)
        return sum(1 for kw in keywords if self._normalize(kw) in text_lower)

    def select_theme(
        self,
        topic: str,
        content: str = "",
        categories: Optional[List[str]] = None,
    ) -> str:
        """Select the best theme for the given topic and optional content.

        Uses rule-based keyword matching across theme categories.

        Args:
            topic: The report topic / title.
            content: Optional additional content for more signal.
            categories: Optional list of category names to consider.
                        Defaults to all categories.

        Returns:
            The selected theme name (CSS filename without extension).
        """
        search_text = f"{topic} {content}".strip()
        if not search_text:
            return self._default_theme

        categories_to_check = categories or list(self._categories.keys())

        best_category = None
        best_score = 0

        for cat_name in categories_to_check:
            if cat_name not in self._categories:
                continue
            cat = self._categories[cat_name]
            score = self._count_matches(search_text, cat["keywords"])
            if score > best_score:
                best_score = score
                best_category = cat_name

        if best_category and best_score > 0:
            themes = self._categories[best_category]["themes"]
            selected = themes[0]
            logger.info(
                "ThemeSelector: topic='%s' matched category='%s' (score=%d), "
                "selected theme='%s'",
                topic[:60], best_category, best_score, selected,
            )
            return selected

        logger.info(
            "ThemeSelector: no category matched for topic='%s', using default='%s'",
            topic[:60], self._default_theme,
        )
        return self._default_theme


theme_selector = ThemeSelector()
