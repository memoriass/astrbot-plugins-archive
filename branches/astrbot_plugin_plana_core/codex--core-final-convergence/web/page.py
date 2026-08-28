"""Assemble the no-build Plana Core dashboard shell."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path


SHELL_ROOT = Path(__file__).resolve().parent / "shell"
PLUGIN_ROOT = SHELL_ROOT.parent.parent
VIEW_FILES = (
    "overview.js",
    "memory-graph.js",
    "memory.js",
    "tasks.js",
    "capabilities.js",
    "resources.js",
    "settings.js",
)


@lru_cache(maxsize=1)
def _shell_sources() -> tuple[str, str, str, str]:
    template = (SHELL_ROOT / "template.html").read_text(encoding="utf-8")
    styles = (SHELL_ROOT / "styles.css").read_text(encoding="utf-8")
    scripts = [
        (SHELL_ROOT / "i18n.js").read_text(encoding="utf-8"),
        *((SHELL_ROOT / "views" / name).read_text(encoding="utf-8") for name in VIEW_FILES),
        (SHELL_ROOT / "app.js").read_text(encoding="utf-8"),
    ]
    plana_art = base64.b64encode((PLUGIN_ROOT / "logo.png").read_bytes()).decode("ascii")
    return template, styles, "\n".join(scripts), f"data:image/png;base64,{plana_art}"


def dashboard_html(api_base: str, *, bridge_mode: bool = False) -> str:
    """Return the full dashboard while keeping all source modules local."""

    template, styles, scripts, plana_art = _shell_sources()
    return (
        template.replace("{{STYLES}}", styles)
        .replace("{{SCRIPTS}}", scripts)
        .replace("{{API_BASE}}", api_base)
        .replace("{{BRIDGE_MODE}}", "true" if bridge_mode else "false")
        .replace("{{PLANA_ART}}", plana_art)
    )
