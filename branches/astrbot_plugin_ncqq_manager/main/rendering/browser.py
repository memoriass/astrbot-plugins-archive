from __future__ import annotations

import os
import pathlib
import tempfile

from astrbot.api import logger

_browser_instance = None
_playwright_instance = None


async def _ensure_browser():
    global _browser_instance, _playwright_instance
    if _browser_instance and _browser_instance.is_connected():
        return _browser_instance
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError:
        logger.warning(
            "playwright 未安装，HTML 卡片渲染不可用，将回退纯文本。"
            "请执行: pip install playwright && playwright install chromium"
        )
        return None
    try:
        _playwright_instance = await async_playwright().start()
        _browser_instance = await _playwright_instance.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--allow-file-access-from-files",
            ]
        )
        logger.info("playwright browser launched (reusable)")
        return _browser_instance
    except Exception as e:
        logger.warning(
            "playwright browser launch failed: %s — "
            "如在 Docker/Linux 环境，请确认已执行 "
            "'playwright install --with-deps chromium'",
            e,
        )
        return None


async def cleanup_renderer() -> None:
    global _browser_instance, _playwright_instance
    if _browser_instance:
        try:
            await _browser_instance.close()
        except Exception:
            pass
        _browser_instance = None
    if _playwright_instance:
        try:
            await _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None
    logger.info("playwright renderer cleaned up")


async def _screenshot_html(html: str, viewport_width: int = 560) -> bytes | None:
    browser = await _ensure_browser()
    if browser is None:
        return None

    tmp_path = None
    page = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".html", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(html)
            tmp_path = f.name

        page = await browser.new_page(viewport={"width": viewport_width, "height": 800})
        file_uri = pathlib.Path(tmp_path).resolve().as_uri()
        await page.goto(file_uri)
        await page.wait_for_load_state("networkidle")
        try:
            await page.wait_for_function(
                """() => {
                    const imgs = document.querySelectorAll('img');
                    return Array.from(imgs).every(img => img.complete);
                }""",
                timeout=5000,
            )
        except Exception:
            pass
        content_box = await page.query_selector("body")
        return await content_box.screenshot() if content_box else await page.screenshot()
    except Exception as e:
        logger.warning("playwright screenshot failed: %s", e)
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
