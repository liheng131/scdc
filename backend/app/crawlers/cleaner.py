from bs4 import BeautifulSoup
from typing import Dict, Any, Tuple

class HTMLCleaner:
    @staticmethod
    def clean(raw_html: str) -> Tuple[str, str, Dict[str, Any]]:
        """Clean HTML to extract title, clean markdown/text and metadata."""
        if not raw_html or not raw_html.strip():
            return "", "", {}

        soup = BeautifulSoup(raw_html, "html.parser")

        # Extract title
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # Extract meta tags
        metadata = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                metadata[name] = content

        # Remove noisy elements
        for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
            element.decompose()

        # Get text
        lines = [line.strip() for line in soup.get_text().splitlines()]
        clean_text = "\n".join([line for line in lines if line])

        return title, clean_text, metadata
