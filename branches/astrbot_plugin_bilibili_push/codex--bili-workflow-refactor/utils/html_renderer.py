from pathlib import Path
import jinja2
from playwright.async_api import Browser, Page, async_playwright
from .logger import logger


class BrowserManager:
    _playwright = None
    _browser: Browser | None = None

    @classmethod
    async def get_browser(cls) -> Browser:
        if cls._browser is None:
            await cls.init()
        return cls._browser

    @classmethod
    async def init(cls):
        if cls._playwright is None:
            cls._playwright = await async_playwright().start()

        if cls._browser is None:
            try:
                cls._browser = await cls._playwright.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
                logger.info("内嵌浏览器启动成功")
            except Exception as exc:
                browser_path = cls._find_system_browser()
                if not browser_path:
                    logger.error(f"启动浏览器失败: {exc}")
                    raise
                logger.warning(f"内嵌浏览器启动失败，尝试系统浏览器: {browser_path}")
                cls._browser = await cls._playwright.chromium.launch(
                    headless=True,
                    executable_path=str(browser_path),
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                logger.info("系统浏览器启动成功")

    @staticmethod
    def _find_system_browser() -> Path | None:
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None


class PageContext:
    def __init__(self, viewport=None, device_scale_factor=1, **kwargs):
        self.viewport = viewport or {"width": 800, "height": 600}
        self.scale_factor = device_scale_factor
        self.page = None

    async def __aenter__(self) -> Page:
        browser = await BrowserManager.get_browser()
        context = await browser.new_context(
            viewport=self.viewport,
            device_scale_factor=self.scale_factor,
            extra_http_headers={"Referer": "https://www.bilibili.com/"},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self.page = await context.new_page()
        return self.page

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.page:
            await self.page.close()
            await self.page.context.close()


async def render_template(
    template_path: Path,
    template_name: str,
    templates: dict,
    viewport: dict = None,
    selector: str = "body",
) -> bytes:
    """渲染模板并截图"""
    if viewport is None:
        viewport = {"width": 800, "height": 600}

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path)),
        enable_async=True,
        autoescape=jinja2.select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_name)
    html_content = await template.render_async(**templates)

    async with PageContext(viewport=viewport, device_scale_factor=2) as page:
        try:
            logger.info(f"[{template_name}] 开始渲染页面内容...")
            await page.set_content(html_content, wait_until="load", timeout=60000)
            logger.info(f"[{template_name}] 页面内容加载完成")
            await page.wait_for_timeout(2000)

            if selector == "body":
                screenshot = await page.screenshot(
                    type="png", full_page=True, omit_background=True
                )
            else:
                logger.debug(f"等待选择器 {selector} 可见...")
                try:
                    await page.wait_for_selector(
                        selector, state="visible", timeout=3000
                    )
                except Exception as e:
                    logger.warning(f"选择器 {selector} 等待超时: {e}")
                locator = page.locator(selector)
                screenshot = await locator.screenshot(
                    type="png", omit_background=True
                )

            return screenshot

        except Exception as e:
            logger.error(f"[{template_name}] 页面渲染/截图失败: {e}")
            raise


class HtmlRenderer:
    def __init__(self, template_path: Path):
        self.template_path = template_path

    async def render(
        self,
        template_name: str,
        templates: dict,
        viewport: dict = None,
        selector: str = "body",
    ) -> bytes:
        return await render_template(
            template_path=self.template_path,
            template_name=template_name,
            templates=templates,
            viewport=viewport,
            selector=selector,
        )
