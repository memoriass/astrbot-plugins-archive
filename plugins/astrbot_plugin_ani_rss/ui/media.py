"""Media loading and caching helpers for rendered cards."""

from __future__ import annotations

import base64
import io
import math
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from astrbot.api import logger

UI_ROOT = Path(__file__).resolve().parent
PLUGIN_LOGO_PATH = UI_ROOT.parent / "logo.png"
COVER_CACHE: dict[str, str] = {}
CARD_LOGO_DATA_URI = ""
MIKAN_ICON_DATA_URI = ""


def source_icon_data_uri(lines: list[str], heading: str) -> str:
    text = "\n".join([heading, *lines]).lower()
    data_uri = mikan_icon_data_uri() if heading.startswith("Mikan") or "mikan" in text else ""
    data_uri = data_uri or card_logo_data_uri()
    if not data_uri:
        return '<div class="source-icon"></div>'
    alt = "Mikan" if heading.startswith("Mikan") or "mikan" in text else "ANI-RSS"
    return (
        '<img class="source-icon" '
        'style="width:42px;height:42px;max-width:42px;max-height:42px;" '
        f'src="{data_uri}" alt="{alt}">'
    )


def mikan_icon_data_uri() -> str:
    global MIKAN_ICON_DATA_URI
    if MIKAN_ICON_DATA_URI:
        return MIKAN_ICON_DATA_URI
    try:
        from PIL import Image, ImageDraw

        size = 84
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 80, 80), radius=18, fill="#ffd24a", outline="#f5b400", width=3)
        draw.ellipse((16, 16, 68, 68), fill="#ffc928", outline="#ffffff", width=5)
        center = (42, 42)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            end = (42 + int(25 * math.cos(radians)), 42 + int(25 * math.sin(radians)))
            draw.line((center, end), fill="#ffffff", width=4)
        draw.ellipse((36, 36, 48, 48), fill="#ffffff")
        image = image.resize((42, 42), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        MIKAN_ICON_DATA_URI = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
    except (ImportError, OSError, ValueError) as exc:
        logger.debug("Failed to build Mikan card icon: %s", exc)
        MIKAN_ICON_DATA_URI = ""
    return MIKAN_ICON_DATA_URI


def card_logo_data_uri() -> str:
    global CARD_LOGO_DATA_URI
    if CARD_LOGO_DATA_URI:
        return CARD_LOGO_DATA_URI
    try:
        from PIL import Image

        image = Image.open(PLUGIN_LOGO_PATH).convert("RGBA")
        bbox = image.getchannel("A").getbbox()
        if bbox:
            image = image.crop(bbox)
        side = max(image.size)
        padding = max(int(side * 0.08), 6)
        canvas = Image.new("RGBA", (side + padding * 2, side + padding * 2), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2))
        canvas.thumbnail((42, 42))
        icon = Image.new("RGBA", (42, 42), (0, 0, 0, 0))
        icon.alpha_composite(canvas, ((42 - canvas.width) // 2, (42 - canvas.height) // 2))
        buffer = io.BytesIO()
        icon.save(buffer, format="PNG")
        CARD_LOGO_DATA_URI = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
    except (ImportError, OSError, ValueError) as exc:
        logger.debug("Failed to load ANI-RSS card logo %s: %s", PLUGIN_LOGO_PATH, exc)
        CARD_LOGO_DATA_URI = ""
    return CARD_LOGO_DATA_URI


def cover_data_uri(url: str, *, cover_proxy: dict[str, Any] | None = None) -> str:
    clean = str(url or "").strip()
    if not clean.startswith(("http://", "https://")):
        return ""
    cache_key = _cover_cache_key(clean, cover_proxy)
    if cache_key in COVER_CACHE:
        return COVER_CACHE[cache_key]
    try:
        raw = _fetch_cover_bytes(clean, cover_proxy=cover_proxy)
        from PIL import Image

        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.thumbnail((96, 96))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        data_uri = f"data:image/png;base64,{encoded}"
    except (ImportError, OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.debug("Failed to load Mikan cover %s: %s", clean, exc)
        data_uri = ""
    COVER_CACHE[cache_key] = data_uri
    return data_uri


def _cover_cache_key(url: str, cover_proxy: dict[str, Any] | None) -> str:
    if not cover_proxy:
        return url
    base_url = str(cover_proxy.get("base_url") or "").rstrip("/")
    api_prefix = str(cover_proxy.get("api_prefix") or "").strip().rstrip("/")
    auth_marker = "auth" if str(cover_proxy.get("api_key") or "").strip() else "anon"
    return f"{url}\0{base_url}{api_prefix}\0{auth_marker}"


def _fetch_cover_bytes(url: str, *, cover_proxy: dict[str, Any] | None = None) -> bytes:
    errors: list[Exception] = []
    for request in _cover_requests(url, cover_proxy=cover_proxy):
        try:
            timeout = _cover_timeout(cover_proxy)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(2_000_000)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            errors.append(exc)
    if errors:
        raise errors[-1]
    raise ValueError("No cover request available.")


def _cover_requests(
    url: str,
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> list[urllib.request.Request]:
    headers = {"User-Agent": "AstrBot ANI-RSS Card"}
    requests: list[urllib.request.Request] = []
    proxy_url = _cover_proxy_url(url, cover_proxy)
    if proxy_url:
        proxy_headers = dict(headers)
        api_key = str((cover_proxy or {}).get("api_key") or "").strip()
        if api_key:
            proxy_headers["api-key"] = api_key
        requests.append(urllib.request.Request(proxy_url, headers=proxy_headers))
    requests.append(urllib.request.Request(url, headers=headers))
    return requests


def _cover_proxy_url(url: str, cover_proxy: dict[str, Any] | None) -> str:
    if not cover_proxy:
        return ""
    base_url = str(cover_proxy.get("base_url") or "").strip().rstrip("/")
    api_prefix = str(cover_proxy.get("api_prefix") or "/api").strip()
    if api_prefix and not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    api_prefix = api_prefix.rstrip("/")
    if not base_url:
        return ""
    encoded = base64.b64encode(url.encode("utf-8")).decode("ascii")
    return f"{base_url}{api_prefix}/proxyImage?imgUrl={urllib.parse.quote(encoded)}"


def _cover_timeout(cover_proxy: dict[str, Any] | None) -> int:
    try:
        return min(max(int((cover_proxy or {}).get("timeout_seconds", 5)), 1), 20)
    except (TypeError, ValueError):
        return 5
