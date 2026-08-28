from __future__ import annotations

import html
from pathlib import Path


DIST_INDEX = Path(__file__).with_name("dist") / "index.html"


def gallery_html(api_base: str = "/api/plug/plana_gallery") -> str:
    if not DIST_INDEX.is_file():
        return _missing_build_html()
    document = DIST_INDEX.read_text(encoding="utf-8")
    return document.replace(
        "__PLANA_GALLERY_API_BASE__",
        html.escape(str(api_base or "/api/plug/plana_gallery"), quote=True),
    )


def _missing_build_html() -> str:
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>Plana Gallery</title><body style="font-family:system-ui;padding:40px">
<h1>Plana Gallery Web 尚未构建</h1>
<p>请在 web/frontend 执行 npm install 和 npm run build。</p></body></html>"""
