import random
import base64
import mimetypes
from pathlib import Path


def get_random_background(folder_path: Path) -> dict:
    """浠庢寚瀹氭枃浠跺す闅忔満鑾峰彇涓€寮犺儗鏅浘锛屽苟杞负 base64 URI"""
    if not folder_path.exists():
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except:
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
    except:
        return {"uri": "", "width": 800, "height": 600}


def get_assets_path() -> Path:
    """获取资源文件根目录"""
    return Path(__file__).parent / "resources"


def get_template_path() -> Path:
    """鑾峰彇妯℃澘鏂囦欢鐩綍"""
    return get_assets_path() / "templates"
