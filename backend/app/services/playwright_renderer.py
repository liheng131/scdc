"""
Playwright 渲染服务（单例）

负责：
1. 启动浏览器实例
2. 将HTML渲染为截图/PDF
3. 管理浏览器生命周期

使用单例模式确保浏览器实例复用，避免重复启动。
"""

import asyncio
import logging
import os
import sys
from typing import List, Optional

logger = logging.getLogger(__name__)


class PlaywrightRenderer:
    """
    Playwright渲染服务（单例）
    
    负责将HTML渲染为截图或PDF。
    使用单例模式确保浏览器实例复用。
    """
    _instance: Optional['PlaywrightRenderer'] = None
    _lock: Optional[asyncio.Lock] = None  # 延迟初始化，避免在模块导入时创建
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.browser = None
        self.playwright = None
        self._initialized = True
    
    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """获取锁实例（延迟初始化）"""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock
    
    async def initialize(self):
        """启动浏览器（延迟初始化）"""
        lock = self._get_lock()
        async with lock:
            if self.browser is None:
                # 启动前打印当前事件循环类型, 便于排查 Windows ProactorEventLoop 问题
                current_loop = asyncio.get_running_loop()
                logger.info(
                    f"[Playwright init] current event loop = {type(current_loop).__name__}, "
                    f"supports_subprocess = {isinstance(current_loop, asyncio.ProactorEventLoop) or hasattr(current_loop, '_make_subprocess_transport') and 'Proactor' in type(current_loop).__name__}"
                )
                if sys.platform == "win32" and not isinstance(current_loop, asyncio.ProactorEventLoop):
                    logger.error(
                        f"[Playwright init] ❌ 当前 event loop 不是 ProactorEventLoop "
                        f"({type(current_loop).__name__}), Playwright 启动浏览器会失败! "
                        f"请用 start_windows.py 启动后端, 或检查 WindowsProactorEventLoopPolicy 是否设置成功。"
                    )
                try:
                    from playwright.async_api import async_playwright
                    self.playwright = await async_playwright().start()
                    
                    # 尝试多种方式启动浏览器
                    launch_options = {
                        "headless": True,
                        "args": ['--no-sandbox', '--disable-setuid-sandbox']
                    }
                    
                    # 方式1：使用环境变量指定的浏览器路径（Docker 环境）
                    import os
                    env_browser_path = os.environ.get('SYSTEM_CHROMIUM_PATH')
                    browser_launched = False
                    
                    if env_browser_path and os.path.exists(env_browser_path):
                        try:
                            launch_options["executable_path"] = env_browser_path
                            self.browser = await self.playwright.chromium.launch(**launch_options)
                            logger.info(f"Using environment browser: {env_browser_path}")
                            browser_launched = True
                        except Exception as e:
                            logger.warning(f"Failed to launch environment browser: {e}")
                    
                    # 方式2：使用系统 Chrome/Edge（如果存在，本地开发环境）
                    if not browser_launched:
                        browser_paths = [
                            # Chrome
                            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
                            # Edge
                            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                            # Linux
                            "/usr/bin/chromium",
                            "/usr/bin/chromium-browser",
                        ]
                        
                        for browser_path in browser_paths:
                            if os.path.exists(browser_path):
                                try:
                                    launch_options["executable_path"] = browser_path
                                    self.browser = await self.playwright.chromium.launch(**launch_options)
                                    logger.info(f"Using system browser: {browser_path}")
                                    browser_launched = True
                                    break
                                except Exception as e:
                                    logger.warning(f"Failed to launch system browser: {e}")
                                    continue
                    
                    # 方式3：使用 Playwright 内置浏览器
                    if not browser_launched:
                        self.browser = await self.playwright.chromium.launch(**launch_options)
                        logger.info("Using Playwright bundled Chromium")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize Playwright: {e}")
                    raise
    
    async def render_to_screenshots(
        self,
        html: str,
        output_dir: str,
        viewport_width: int = 1920,
        viewport_height: int = 1080
    ) -> List[str]:
        """
        将HTML渲染为多张截图（每页一张）

        实现方案:
        1. 把 HTML 写到 static/html-ppt/_tmp_deck_*.html, 让 assets 相对路径可解析
        2. Playwright 加载 file:// URL, 模拟 print 媒体 (html-ppt 的 @media print 让所有 .slide 可见)
        3. 用 page.screenshot(full_page=True) 截取整页 (所有 slide 都在)
        4. 用 PIL 按 slide 数量切片, 每张 slide 切成一张 PNG

        为什么不直接用 element.screenshot():
        - html-ppt 的 slide 在 print 模式下 position:relative; height:100vh
        - 多个 slide 会在视口里堆叠, element.screenshot() 经常报"element is not visible"
        - 用 full_page + 切片更稳定, 也保证所有 slide 视觉一致

        Args:
            html: 完整的HTML字符串
            output_dir: 输出目录
            viewport_width: 视口宽度
            viewport_height: 视口高度

        Returns:
            截图文件路径列表
        """
        await self.initialize()

        page = await self.browser.new_page(
            viewport={'width': viewport_width, 'height': viewport_height}
        )

        try:
            tmp_html_path = await self._write_html_to_static_dir(html)
            file_url = f"file:///{tmp_html_path.replace(os.sep, '/')}"
            logger.debug(f"Loading HTML from: {file_url}")
            await page.goto(file_url, wait_until='networkidle')

            # 强制 print 媒体模式 —— html-ppt 的 @media print 让所有 .slide 可见
            await page.emulate_media(media="print")
            # 等动画完成
            await page.wait_for_timeout(1500)

            # 在 print 模式下强制让所有 .slide 块级化、占满 100vh,
            # 这样 page.screenshot(full_page=True) 才能截到全部高度
            await page.evaluate(f"""
                () => {{
                    const deck = document.querySelector('.deck');
                    if (deck) {{
                        deck.style.display = 'block';
                        deck.style.position = 'static';
                        deck.style.width = '100%';
                        deck.style.height = 'auto';
                        deck.style.overflow = 'visible';
                    }}
                    const slides = document.querySelectorAll('.slide');
                    slides.forEach((s, i) => {{
                        s.classList.add('is-active');
                        s.style.position = 'relative';
                        s.style.opacity = '1';
                        s.style.transform = 'none';
                        s.style.pointerEvents = 'auto';
                        s.style.width = '100%';
                        s.style.height = '{viewport_height}px';
                        s.style.minHeight = '{viewport_height}px';
                        s.style.maxHeight = '{viewport_height}px';
                        s.style.display = 'block';
                        s.style.inset = 'auto';
                        s.style.pageBreakAfter = 'always';
                        s.style.overflow = 'hidden';
                    }});
                    // 触发重排
                    void document.body.offsetHeight;
                }}
            """)
            # 等待样式生效
            await page.wait_for_timeout(500)

            # 获取所有 slide
            slides = await page.query_selector_all('.slide')
            slide_count = len(slides)
            if slide_count == 0:
                logger.warning("No .slide elements found in HTML")
                path = os.path.join(output_dir, 'slide_001.png')
                await page.screenshot(path=path, full_page=True)
                return [path]

            # 整页截图
            full_path = os.path.join(output_dir, '_full_page.png')
            await page.screenshot(path=full_path, full_page=True)
            logger.debug(f"Full page screenshot: {full_path}")

            # 按 slide 数量切片
            try:
                from PIL import Image
            except ImportError:
                logger.warning("PIL not available, falling back to element.screenshot")
                # 降级: 用 element.screenshot 逐个截
                screenshot_paths = []
                for i, slide in enumerate(slides):
                    path = os.path.join(output_dir, f'slide_{i+1:03d}.png')
                    await slide.screenshot(path=path, timeout=30000)
                    screenshot_paths.append(path)
                return screenshot_paths

            full_img = Image.open(full_path)
            img_width, img_height = full_img.size
            slide_height = img_height // slide_count
            logger.info(
                f"Slicing full page {img_width}x{img_height} into {slide_count} "
                f"slides of {img_width}x{slide_height}"
            )

            screenshot_paths = []
            for i in range(slide_count):
                top = i * slide_height
                bottom = (i + 1) * slide_height if i < slide_count - 1 else img_height
                slide_img = full_img.crop((0, top, img_width, bottom))
                path = os.path.join(output_dir, f'slide_{i+1:03d}.png')
                slide_img.save(path, 'PNG', optimize=True)
                screenshot_paths.append(path)
                logger.debug(f"Screenshot saved: {path}")

            # 删除整页临时图
            try:
                os.unlink(full_path)
            except Exception:
                pass

            return screenshot_paths
        finally:
            await page.close()
            try:
                if 'tmp_html_path' in locals() and os.path.exists(tmp_html_path):
                    os.unlink(tmp_html_path)
            except Exception:
                pass

    async def _write_html_to_static_dir(self, html: str) -> str:
        """把 HTML 写入 app/static/html-ppt/ 临时文件, 使 assets 相对路径可解析

        Returns:
            临时文件的绝对路径
        """
        import tempfile
        import uuid
        # 找到后端 app/static/html-ppt 目录
        # playwright_renderer.py 在 app/services/, 上溯 2 层到 app/, 再到 static/html-ppt
        services_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(services_dir)
        static_dir = os.path.join(app_dir, "static", "html-ppt")
        os.makedirs(static_dir, exist_ok=True)

        # 使用唯一文件名
        filename = f"_tmp_deck_{uuid.uuid4().hex[:8]}.html"
        file_path = os.path.join(static_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        return file_path

    async def render_to_pdf(
        self,
        html: str,
        output_path: str,
        width: str = '1920px',
        height: str = '1080px'
    ):
        """
        将HTML渲染为PDF

        Args:
            html: 完整的HTML字符串
            output_path: PDF输出路径
            width: 页面宽度
            height: 页面高度
        """
        await self.initialize()

        page = await self.browser.new_page(
            viewport={'width': 1920, 'height': 1080}
        )

        try:
            tmp_html_path = await self._write_html_to_static_dir(html)
            file_url = f"file:///{tmp_html_path.replace(os.sep, '/')}"
            await page.goto(file_url, wait_until='networkidle')

            # 强制 print 媒体模式 + 让所有 .slide 可见（与 render_to_screenshots 一致）
            await page.emulate_media(media="print")
            await page.wait_for_timeout(1500)

            await page.evaluate("""
                () => {
                    const deck = document.querySelector('.deck');
                    if (deck) {
                        deck.style.display = 'block';
                        deck.style.position = 'static';
                        deck.style.width = '100%';
                        deck.style.height = 'auto';
                        deck.style.overflow = 'visible';
                    }
                    const slides = document.querySelectorAll('.slide');
                    slides.forEach((s) => {
                        s.classList.add('is-active');
                        s.style.position = 'relative';
                        s.style.opacity = '1';
                        s.style.transform = 'none';
                        s.style.pointerEvents = 'auto';
                        s.style.width = '100%';
                        s.style.display = 'block';
                        s.style.inset = 'auto';
                        s.style.pageBreakAfter = 'always';
                        s.style.overflow = 'hidden';
                    });
                    void document.body.offsetHeight;
                }
            """)
            await page.wait_for_timeout(500)

            await page.pdf(
                path=output_path,
                width=width,
                height=height,
                print_background=True,
                margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'}
            )

            logger.info(f"PDF saved: {output_path}")
        finally:
            await page.close()
            try:
                if 'tmp_html_path' in locals() and os.path.exists(tmp_html_path):
                    os.unlink(tmp_html_path)
            except Exception:
                pass
    
    async def close(self):
        """关闭浏览器"""
        lock = self._get_lock()
        async with lock:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            logger.info("Playwright browser closed")
    
    @classmethod
    async def cleanup(cls):
        """清理单例资源"""
        if cls._instance:
            await cls._instance.close()
            cls._instance = None
