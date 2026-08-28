import random
import base64
import mimetypes
from pathlib import Path


_INTERNAL_FONT_FAMILY = "BiliPushNotoSansSC"
_INTERNAL_FONT_BASE_URL = "https://astrbot-plugin.local/fonts"
_INTERNAL_FONT_FILES = {
    400: "noto-sans-sc-chinese-simplified-400-normal.woff2",
    700: "noto-sans-sc-chinese-simplified-700-normal.woff2",
}


def get_random_background(folder_path: Path) -> dict:
    """随机读取背景图并转为 data URI。"""
    if not folder_path.exists():
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return {"uri": "", "width": 800, "height": 600}

    bg_files = [
        f
        for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
    ]

    if not bg_files:
        return {"uri": "", "width": 800, "height": 600}

    bg_file = random.choice(bg_files)
    try:
        mime_type, _ = mimetypes.guess_type(bg_file)
        with open(bg_file, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            return {
                "uri": f"data:{mime_type or 'image/jpeg'};base64,{b64_data}",
                "width": 800,
                "height": 600,
            }
    except Exception:
        return {"uri": "", "width": 800, "height": 600}


def get_assets_path() -> Path:
    """获取资源文件根目录"""
    return Path(__file__).parent / "resources"


def get_fonts_path() -> Path:
    """获取内置字体目录。"""
    return get_assets_path() / "fonts"


def get_template_path() -> Path:
    """获取模板目录。"""
    return get_assets_path() / "templates"


def get_internal_font_family() -> str:
    return _INTERNAL_FONT_FAMILY


def get_internal_font_routes() -> dict[str, Path]:
    routes = {}
    font_dir = get_fonts_path()
    for file_name in _INTERNAL_FONT_FILES.values():
        path = font_dir / file_name
        if path.exists():
            routes[f"{_INTERNAL_FONT_BASE_URL}/{file_name}"] = path
    return routes


def get_internal_font_face_css() -> str:
    routes = get_internal_font_routes()
    blocks = []
    for weight, file_name in _INTERNAL_FONT_FILES.items():
        url = f"{_INTERNAL_FONT_BASE_URL}/{file_name}"
        if url not in routes:
            continue
        blocks.append(
            "\n".join(
                (
                    "@font-face {",
                    f"  font-family: '{_INTERNAL_FONT_FAMILY}';",
                    "  font-style: normal;",
                    f"  font-weight: {weight};",
                    "  font-display: swap;",
                    f"  src: url('{url}') format('woff2');",
                    "}",
                )
            )
        )
    return "\n".join(blocks)
