from pathlib import Path
import asyncio
import time

import jinja2
from playwright.async_api import Browser, Page, async_playwright
from .logger import logger
from .resource import (
    get_internal_font_face_css,
    get_internal_font_family,
    get_internal_font_routes,
)
from .image_optimizer import DEFAULT_AVATAR_DATA_URI, localize_template_avatar_images


_CONTENT_TIMEOUT_MS = 15000
_RESOURCE_IDLE_TIMEOUT_MS = 8000
_IMAGE_WAIT_TIMEOUT_MS = 8000
_FONT_WAIT_TIMEOUT_MS = 3000
_POST_LOAD_WAIT_MS = 500
_RENDER_RETRIES = 1
_BROWSER_MAX_RENDER_COUNT = 200
_BROWSER_MAX_AGE_SEC = 6 * 60 * 60
_RENDER_SEMAPHORE = asyncio.Semaphore(2)


class BrowserManager:
    _playwright = None
    _browser: Browser | None = None
    _init_lock: asyncio.Lock | None = None
    _browser_started_at = 0.0
    _render_count = 0
    _consecutive_failures = 0
    _active_contexts = 0

    @classmethod
    async def get_browser(cls) -> Browser:
        if cls._browser is None:
            await cls.init()
        return cls._browser

    @classmethod
    async def init(cls):
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            if cls._playwright is None:
                cls._playwright = await async_playwright().start()

            if cls._browser is None:
                try:
                    cls._browser = await cls._playwright.chromium.launch(
                        headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
                    )
                    cls._browser_started_at = time.monotonic()
                    cls._render_count = 0
                    cls._consecutive_failures = 0
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
                    cls._browser_started_at = time.monotonic()
                    cls._render_count = 0
                    cls._consecutive_failures = 0
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
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            await cls._close_locked(stop_playwright=True)

    @classmethod
    async def prepare_context(cls) -> None:
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            if cls._active_contexts == 0 and cls._should_recycle_locked():
                await cls._close_locked(stop_playwright=False)
            cls._active_contexts += 1

    @classmethod
    async def release_context(cls) -> None:
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            cls._active_contexts = max(0, cls._active_contexts - 1)

    @classmethod
    async def record_render_success(cls) -> None:
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            cls._render_count += 1
            cls._consecutive_failures = 0
            if cls._active_contexts == 0 and cls._should_recycle_locked():
                await cls._close_locked(stop_playwright=False)

    @classmethod
    async def record_render_failure(cls) -> None:
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            cls._consecutive_failures += 1

    @classmethod
    async def recycle(cls, reason: str, *, stop_playwright: bool = False) -> None:
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()

        async with cls._init_lock:
            if cls._active_contexts > 0:
                logger.warning(f"浏览器仍有活动页面，暂不回收: {reason}")
                return
            logger.warning(f"回收内嵌浏览器: {reason}")
            await cls._close_locked(stop_playwright=stop_playwright)

    @classmethod
    def _should_recycle_locked(cls) -> bool:
        if cls._browser is None:
            return False
        if cls._render_count >= _BROWSER_MAX_RENDER_COUNT:
            return True
        if cls._browser_started_at and time.monotonic() - cls._browser_started_at > _BROWSER_MAX_AGE_SEC:
            return True
        return False

    @classmethod
    async def _close_locked(cls, *, stop_playwright: bool) -> None:
        if cls._browser:
            try:
                await cls._browser.close()
            finally:
                cls._browser = None
        cls._browser_started_at = 0.0
        cls._render_count = 0
        cls._consecutive_failures = 0
        if stop_playwright and cls._playwright:
            try:
                await cls._playwright.stop()
            finally:
                cls._playwright = None


class PageContext:
    def __init__(self, viewport=None, device_scale_factor=1, **kwargs):
        self.viewport = viewport or {"width": 800, "height": 600}
        self.scale_factor = device_scale_factor
        self.context = None
        self.page = None

    async def __aenter__(self) -> Page:
        await BrowserManager.prepare_context()
        try:
            browser = await BrowserManager.get_browser()
            self.context = await browser.new_context(
                viewport=self.viewport,
                device_scale_factor=self.scale_factor,
                extra_http_headers={"Referer": "https://www.bilibili.com/"},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            self.page = await self.context.new_page()
            return self.page
        except Exception:
            await BrowserManager.release_context()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.page:
                await self.page.close()
        finally:
            try:
                self.page = None
                if self.context:
                    await self.context.close()
            finally:
                self.context = None
                await BrowserManager.release_context()


async def _wait_for_page_resources(page: Page, template_name: str) -> None:
    try:
        await page.wait_for_function(
            "() => !document.fonts || document.fonts.status === 'loaded'",
            timeout=_FONT_WAIT_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.warning(f"[{template_name}] 字体加载等待超时，继续截图: {exc}")

    try:
        await page.wait_for_load_state("networkidle", timeout=_RESOURCE_IDLE_TIMEOUT_MS)
    except Exception as exc:
        logger.warning(f"[{template_name}] 页面资源加载等待超时，继续截图: {exc}")

    try:
        await page.wait_for_function(
            "() => Array.from(document.images).every(img => img.complete)",
            timeout=_IMAGE_WAIT_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.warning(f"[{template_name}] 图片加载等待超时，继续截图: {exc}")


async def _register_internal_font_routes(page: Page) -> None:
    for url, font_path in get_internal_font_routes().items():
        async def fulfill_font(route, request, path=font_path):
            await route.fulfill(path=str(path), content_type="font/woff2")

        await page.route(url, fulfill_font)


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
    env.globals.update(
        default_avatar_data_uri=DEFAULT_AVATAR_DATA_URI,
        internal_font_face_css=get_internal_font_face_css(),
        internal_font_family=get_internal_font_family(),
    )
    template = env.get_template(template_name)
    html_content = await template.render_async(**templates)

    async with _RENDER_SEMAPHORE:
        start = time.perf_counter()
        async with PageContext(viewport=viewport, device_scale_factor=2) as page:
            try:
                logger.info(f"[{template_name}] 开始渲染页面内容...")
                await _register_internal_font_routes(page)
                await page.set_content(
                    html_content,
                    wait_until="domcontentloaded",
                    timeout=_CONTENT_TIMEOUT_MS,
                )
                await _wait_for_page_resources(page, template_name)
                logger.info(f"[{template_name}] 页面内容加载完成")
                await page.wait_for_timeout(_POST_LOAD_WAIT_MS)

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

                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.info(f"[{template_name}] 页面截图完成，用时 {elapsed_ms}ms")
                return screenshot

            except Exception as e:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.error(f"[{template_name}] 页面渲染/截图失败，用时 {elapsed_ms}ms: {e}")
                raise


class HtmlRenderer:
    def __init__(self, template_path: Path, avatar_cache_dir: Path | None = None):
        self.template_path = template_path
        self.avatar_cache_dir = avatar_cache_dir

    async def render(
        self,
        template_name: str,
        templates: dict,
        viewport: dict = None,
        selector: str = "body",
    ) -> bytes:
        last_error = None
        render_templates = await localize_template_avatar_images(
            templates,
            self.avatar_cache_dir,
        )
        for attempt in range(_RENDER_RETRIES + 1):
            try:
                image = await render_template(
                    template_path=self.template_path,
                    template_name=template_name,
                    templates=render_templates,
                    viewport=viewport,
                    selector=selector,
                )
                await BrowserManager.record_render_success()
                return image
            except Exception as exc:
                last_error = exc
                await BrowserManager.record_render_failure()
                if attempt >= _RENDER_RETRIES:
                    break
                logger.warning(
                    f"[{template_name}] 渲染失败，回收浏览器后重试 {attempt + 1}/{_RENDER_RETRIES}: {exc}"
                )
                await BrowserManager.recycle(
                    "render retry",
                    stop_playwright=True,
                )
        raise last_error
