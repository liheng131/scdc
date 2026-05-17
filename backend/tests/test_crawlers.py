import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.deps import get_current_active_user
from app.models.user import User
from app.crawlers.cleaner import HTMLCleaner
from app.crawlers.http_crawler import HTTPCrawler
from app.schemas.crawler import CrawlRequest

def test_html_cleaner():
    html = '''
    <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="Test description">
        </head>
        <body>
            <nav>Menu 1 | Menu 2</nav>
            <h1>Main Title</h1>
            <p>This is the main article text.</p>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    '''
    title, clean_text, metadata = HTMLCleaner.clean(html)
    assert title == "Test Page"
    assert metadata["description"] == "Test description"
    assert "Main Title" in clean_text
    assert "This is the main article text." in clean_text
    assert "Menu 1" not in clean_text
    assert "Copyright" not in clean_text

@pytest.mark.asyncio
async def test_crawler_degradation():
    crawler = HTTPCrawler()
    # Test invalid url that fails immediately
    req = CrawlRequest(url="http://invalid.nonexistent.domain.test", timeout=2)
    res = await crawler.crawl(req)
    assert res.success is False
    assert res.error is not None
    assert res.url == req.url

@pytest.mark.asyncio
async def test_crawler_api():
    mock_user = User(id=1, username="test", role="admin", status="active")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Request invalid endpoint to test API degradation
        req = {"url": "http://invalid.nonexistent.domain.test", "timeout": 2}
        res = await ac.post("/api/v1/crawlers/crawl", json=req)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["success"] is False
        assert data["error"] is not None
