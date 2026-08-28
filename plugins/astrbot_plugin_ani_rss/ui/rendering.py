from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .blocks import extract_heading as _extract_heading
from .generic_cards import build_generic_card_html, is_success_card_text
from .mikan_cards import (
    build_mikan_card_html,
    is_mikan_card_text,
    mikan_render_width,
)
from .subscription_cards import (
    build_subscription_list_card_html,
    is_subscription_list_text,
)

_PYLITEHTML_UNAVAILABLE_LOGGED = False


def render_card_png(
    text: str,
    *,
    output_dir: str = "",
    width: int = 860,
    scale: int = 2,
    title: str = "",
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    _setup_pylitehtml_fonts()
    from pylitehtml import FontConfig, html_to_png

    output_root = Path(output_dir).expanduser() if output_dir else _default_output_dir()
    output_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    path = output_root / f"ani_rss_card_{int(time.time())}_{digest}.png"
    render_width = _render_width(text, title=title, requested_width=max(int(width), 420))
    render_scale = 1 if _uses_compact_scale(text, title=title) else max(int(scale), 1)
    document = build_card_html(text, title=title, cover_proxy=cover_proxy)
    png = html_to_png(
        document,
        width=render_width,
        scale=render_scale,
        wrap=False,
        shrink_to_fit=True,
        fonts=FontConfig(default="sans-serif"),
    )
    path.write_bytes(png)
    return str(path)


async def result_for_interaction(plugin: Any, event: Any, text: str, *, title: str = "") -> tuple[Any, str]:
    mode = plugin.render_mode()
    if mode == "text":
        return event.plain_result(text), ""
    if not _pylitehtml_available():
        _log_pylitehtml_unavailable()
        return event.plain_result(text), ""

    try:
        cover_proxy = {}
        cover_proxy_config = getattr(plugin, "cover_proxy_config", None)
        if callable(cover_proxy_config):
            cover_proxy = cover_proxy_config()
        path = await asyncio.to_thread(
            render_card_png,
            text,
            output_dir=plugin.render_output_dir(),
            width=plugin.render_width(),
            scale=plugin.render_scale(),
            title=title,
            cover_proxy=cover_proxy,
        )
    except Exception as exc:
        logger.warning("ANI-RSS card render failed, fallback to text: %s", exc)
        return event.plain_result(text), ""

    if mode == "both":
        return event.make_result().file_image(path).message("\n" + compact_caption(text)), path
    return event.image_result(path), path


def cleanup_rendered_cards(paths: list[str]) -> None:
    while paths:
        path = paths.pop()
        if not path:
            continue
        try:
            Path(path).unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("Failed to remove ANI-RSS rendered card %s: %s", path, exc)


def compact_caption(text: str, *, limit: int = 180) -> str:
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("|---"):
            continue
        if clean.startswith("|"):
            continue
        lines.append(clean)
        if len(" ".join(lines)) >= limit:
            break
    caption = " ".join(lines)
    return caption[:limit].rstrip()


def build_card_html(
    text: str,
    *,
    title: str = "",
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    text = text.strip()
    lines = [line.rstrip() for line in text.splitlines()]
    heading, subtitle, body_lines = _extract_heading(lines, title=title)
    mikan_card = build_mikan_card_html(
        heading,
        subtitle,
        body_lines,
        cover_proxy=cover_proxy,
    )
    if mikan_card:
        return mikan_card
    subscription_card = build_subscription_list_card_html(
        heading,
        subtitle,
        body_lines,
        cover_proxy=cover_proxy,
    )
    if subscription_card:
        return subscription_card

    return build_generic_card_html(lines, heading, subtitle, body_lines)


def _render_width(text: str, *, title: str = "", requested_width: int = 860) -> int:
    if is_mikan_card_text(text, title=title):
        return mikan_render_width(text, title=title, requested_width=requested_width)
    if is_subscription_list_text(text, title=title):
        return 860
    if _is_mikan_group_text(text, title=title):
        return 500
    if is_success_card_text(text, title=title):
        return 560
    return requested_width


def _uses_compact_scale(text: str, *, title: str = "") -> bool:
    return (
        is_mikan_card_text(text, title=title)
        or is_subscription_list_text(text, title=title)
        or _is_mikan_group_text(text, title=title)
        or is_success_card_text(text, title=title)
    )


def _is_mikan_group_text(text: str, *, title: str = "") -> bool:
    lines = [line.rstrip() for line in str(text or "").strip().splitlines()]
    heading, _, _ = _extract_heading(lines, title=title)
    return heading.startswith("Mikan 字幕组 RSS")


def _default_output_dir() -> Path:
    return Path(tempfile.gettempdir()) / "astrbot_plugin_ani_rss"


def _setup_pylitehtml_fonts() -> None:
    if os.environ.get("FONTCONFIG_FILE"):
        return
    spec = importlib.util.find_spec("pylitehtml")
    if not spec or not spec.origin:
        return
    fonts_dir = Path(spec.origin).resolve().parent / "fonts"
    fonts_conf = fonts_dir / "fonts.conf"
    if fonts_conf.exists():
        os.environ["FONTCONFIG_FILE"] = str(fonts_conf)
        os.environ.setdefault("FONTCONFIG_PATH", str(fonts_dir))


def _pylitehtml_available() -> bool:
    return importlib.util.find_spec("pylitehtml") is not None


def _log_pylitehtml_unavailable() -> None:
    global _PYLITEHTML_UNAVAILABLE_LOGGED
    if _PYLITEHTML_UNAVAILABLE_LOGGED:
        return
    logger.info("pylitehtml is not installed; ANI-RSS card rendering falls back to text.")
    _PYLITEHTML_UNAVAILABLE_LOGGED = True
