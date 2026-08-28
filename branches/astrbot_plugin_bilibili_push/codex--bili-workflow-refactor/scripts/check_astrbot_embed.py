from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
ASTRBOT_ROOT = Path(os.environ.get("ASTRBOT_ROOT", r"C:\git\AstrBot"))
PLUGIN_NAME = "astrbot_plugin_bilibili_push"
PAGE_NAME = "manager"


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key in {"src", "href"} and value:
                self.assets.append(value)


def main() -> None:
    _check_metadata()
    _check_astrbot_page_contract()
    _check_page_assets()
    registered = _registered_web_endpoints()
    bridge_calls = _bridge_calls()
    missing = sorted(bridge_calls - registered)
    if missing:
        raise SystemExit(f"manager bridge endpoints are not registered: {missing}")
    print("astrbot_embed_check=ok")
    print(f"plugin_name={PLUGIN_NAME}")
    print(f"page={PAGE_NAME}")
    print("bridge_endpoints=" + ",".join(sorted(bridge_calls)))


def _check_metadata() -> None:
    metadata = _read_simple_yaml(ROOT / "metadata.yaml")
    if metadata.get("name") != PLUGIN_NAME:
        raise SystemExit(
            "metadata.yaml name must match the Web API prefix used by AstrBot bridge"
        )
    if metadata.get("repo") != "https://github.com/memoriass/astrbot_plugin_bilibili_push":
        raise SystemExit("metadata.yaml repo is missing or points to the wrong project")
    if "description" not in metadata and "desc" not in metadata:
        raise SystemExit("metadata.yaml must expose description or desc")
    _check_plugin_logo()


def _check_plugin_logo() -> None:
    logo = ROOT / "logo.png"
    if not logo.exists():
        raise SystemExit("plugin logo.png is missing")

    with logo.open("rb") as file:
        signature = file.read(26)

    if not signature.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit("plugin logo.png must be a PNG file")

    width = int.from_bytes(signature[16:20], "big")
    height = int.from_bytes(signature[20:24], "big")
    if (width, height) != (256, 256):
        raise SystemExit("plugin logo.png must be 256x256 as recommended by AstrBot")

    color_type = signature[25] if len(signature) > 25 else None
    if color_type not in {4, 6}:
        raise SystemExit("plugin logo.png must include an alpha channel")


def _read_simple_yaml(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip("'\"")
    return result


def _check_astrbot_page_contract() -> None:
    plugin_route = ASTRBOT_ROOT / "astrbot" / "dashboard" / "routes" / "plugin.py"
    bridge = ASTRBOT_ROOT / "astrbot" / "dashboard" / "plugin_page_bridge.js"
    page_view = ASTRBOT_ROOT / "dashboard" / "src" / "views" / "PluginPagePage.vue"
    server = ASTRBOT_ROOT / "astrbot" / "dashboard" / "server.py"
    context = ASTRBOT_ROOT / "astrbot" / "core" / "star" / "context.py"
    for path in [plugin_route, bridge, page_view, server, context]:
        if not path.exists():
            raise SystemExit(f"AstrBot source file is missing: {path}")

    route_source = plugin_route.read_text(encoding="utf-8")
    if '_PLUGIN_PAGE_ROOT_DIR_NAME = "pages"' not in route_source:
        raise SystemExit("AstrBot Plugin Pages root is not pages/")
    if '_PLUGIN_PAGE_ENTRY_FILE_NAME = "index.html"' not in route_source:
        raise SystemExit("AstrBot Plugin Pages entry file is not index.html")
    if "/api/plugin/page/bridge-sdk.js" not in route_source:
        raise SystemExit("AstrBot Plugin Pages bridge injection contract changed")

    bridge_source = bridge.read_text(encoding="utf-8")
    if "window.AstrBotPluginPage" not in bridge_source:
        raise SystemExit("AstrBot bridge global is missing")
    if "apiGet(endpoint, params)" not in bridge_source:
        raise SystemExit("AstrBot bridge apiGet is missing")
    if "apiPost(endpoint, body)" not in bridge_source:
        raise SystemExit("AstrBot bridge apiPost is missing")

    view_source = page_view.read_text(encoding="utf-8")
    if "`/api/plug/${encodeURIComponent(pluginName.value)}/${normalized}`" not in view_source:
        raise SystemExit("Dashboard no longer prefixes bridge requests with plugin name")

    if "/api/plug/<path:subpath>" not in server.read_text(encoding="utf-8"):
        raise SystemExit("AstrBot dashboard /api/plug route is missing")
    if "def register_web_api(" not in context.read_text(encoding="utf-8"):
        raise SystemExit("AstrBot star context register_web_api is missing")


def _check_page_assets() -> None:
    page_root = ROOT / "pages" / PAGE_NAME
    index = page_root / "index.html"
    if not index.exists():
        raise SystemExit("manager Plugin Page entry is missing")
    html = index.read_text(encoding="utf-8")
    if "/api/plug/" in html or "bridge-sdk.js" in html:
        raise SystemExit("manager page must let AstrBot inject bridge and API prefixing")

    parser = AssetParser()
    parser.feed(html)
    for asset in parser.assets:
        _assert_local_asset_exists(page_root, asset)
    for css_path in page_root.glob("*.css"):
        _check_css_urls(page_root, css_path)
    for js_path in page_root.glob("*.js"):
        _check_js_imports(page_root, js_path)
        source = js_path.read_text(encoding="utf-8")
        forbidden = ["/api/plug/", "document.cookie", "localStorage", "sessionStorage"]
        leaked = [item for item in forbidden if item in source]
        if leaked:
            raise SystemExit(f"forbidden dashboard coupling in {js_path.name}: {leaked}")


def _assert_local_asset_exists(base: Path, raw_url: str) -> None:
    if _is_external_or_special(raw_url):
        return
    path = urlsplit(raw_url).path
    target = (base / path).resolve(strict=False)
    target.relative_to(base.resolve())
    if not target.exists():
        raise SystemExit(f"missing manager page asset: {raw_url}")


def _check_css_urls(page_root: Path, css_path: Path) -> None:
    source = css_path.read_text(encoding="utf-8")
    for raw_url in re.findall(r"url\((?:'|\")?([^'\"\)]+)(?:'|\")?\)", source):
        _assert_local_asset_exists(css_path.parent, raw_url.strip())


def _check_js_imports(page_root: Path, js_path: Path) -> None:
    source = js_path.read_text(encoding="utf-8")
    for raw_url in re.findall(r"from\s+[\"']([^\"']+)[\"']", source):
        if raw_url.startswith(("./", "../")):
            _assert_local_asset_exists(js_path.parent, raw_url)


def _is_external_or_special(raw_url: str) -> bool:
    value = raw_url.strip().lower()
    return (
        not value
        or value.startswith(("#", "data:", "blob:", "http://", "https://", "//"))
        or value.startswith(("mailto:", "tel:", "javascript:"))
    )


def _registered_web_endpoints() -> set[str]:
    source = (ROOT / "webapi" / "manager_api.py").read_text(encoding="utf-8")
    if f'PLUGIN_NAME = "{PLUGIN_NAME}"' not in source:
        raise SystemExit("webapi manager prefix does not match plugin name")
    return set(re.findall(r'\("([^"]+)",\s*api\.', source))


def _bridge_calls() -> set[str]:
    source = (ROOT / "pages" / PAGE_NAME / "api.js").read_text(encoding="utf-8")
    return set(re.findall(r'api(?:Get|Post)\("([^"]+)"', source))


if __name__ == "__main__":
    main()
