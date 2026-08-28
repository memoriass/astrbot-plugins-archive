"""HTML → Image renderer for ncqq instance list.

Priority chain:
  1. playwright (headless chromium) → PNG bytes → Image.fromBase64
  2. plain-text fallback (always available)
"""
from __future__ import annotations

import datetime
import html
import os
import pathlib
import random
import struct
from typing import Union

from astrbot.api import logger

from .browser import cleanup_renderer, _ensure_browser, _screenshot_html

_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "templates" / "instances.html"

_BINDINGS_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "templates" / "bindings.html"

_bindings_template_cache: str | None = None
_bindings_template_mtime: float = 0.0

# 模板文件缓存：避免每次渲染都读磁盘
_template_cache: str | None = None
_template_mtime: float = 0.0

# 壁纸目录：运行时由 main.py 通过 set_bg_dir() 设置为 plugin data 路径
_BG_DIR: pathlib.Path | None = None

# 支持的壁纸扩展名
_BG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# 壁纸缓存：基于目录 mtime 自动失效，每条记录为 (file_uri, pixel_width)
_wallpaper_cache: list[tuple[str, int]] = []
_wallpaper_dir_mtime: float = 0.0

# 无壁纸时的默认面板宽度
_DEFAULT_BODY_W = 560

def _html(value: object, *, quote: bool = True) -> str:
    return html.escape(str(value or ""), quote=quote)


def set_bg_dir(path: pathlib.Path) -> None:
    """由 main.py 初始化时调用，设置壁纸存储目录（plugin data/backgrounds）。"""
    global _BG_DIR, _wallpaper_cache, _wallpaper_dir_mtime
    _BG_DIR = path
    # 切换目录时清除缓存
    _wallpaper_cache = []
    _wallpaper_dir_mtime = 0.0


def _image_width(data: bytes) -> int:
    """从图片二进制数据中快速读取像素宽度（支持 JPEG/PNG/WebP）。"""
    try:
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            # PNG: IHDR chunk, width at offset 16 (4 bytes big-endian)
            return struct.unpack('>I', data[16:20])[0]
        if data[:2] == b'\xff\xd8':
            # JPEG: 扫描 SOFn 标记
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    return struct.unpack('>H', data[i + 7:i + 9])[0]
                length = struct.unpack('>H', data[i + 2:i + 4])[0]
                i += 2 + length
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            # WebP VP8: width at offset 26 (little-endian 14-bit)
            if data[12:16] == b'VP8 ':
                return (struct.unpack('<H', data[26:28])[0]) & 0x3FFF
            # WebP VP8L
            if data[12:16] == b'VP8L':
                bits = struct.unpack('<I', data[21:25])[0]
                return (bits & 0x3FFF) + 1
    except Exception:
        pass
    return _DEFAULT_BODY_W  # 无法解析时回退默认宽度


def _load_wallpapers() -> list[tuple[str, int]]:
    """扫描 backgrounds/ 目录，返回 [(file_uri, pixel_width), ...] 列表。

    使用 file:// URI 直接引用本地文件，避免 base64 编码占用大量内存。
    Playwright 通过 file:// 协议加载 HTML，可直接访问本地文件。
    使用 mtime 缓存：目录修改时间不变时直接返回上次结果。
    """
    global _wallpaper_cache, _wallpaper_dir_mtime
    if _BG_DIR is None or not _BG_DIR.is_dir():
        return []
    try:
        current_mtime = _BG_DIR.stat().st_mtime
    except OSError:
        return []
    if _wallpaper_cache and current_mtime == _wallpaper_dir_mtime:
        return _wallpaper_cache
    entries: list[tuple[str, int]] = []
    for f in _BG_DIR.iterdir():
        if f.suffix.lower() not in _BG_EXTS:
            continue
        try:
            # 只读取少量头部字节来获取宽度，不再全量读取
            raw = f.read_bytes()
            width = _image_width(raw)
            # 使用 file:// URI，避免 base64 编码大图占内存
            file_uri = pathlib.Path(f).resolve().as_uri()
            entries.append((file_uri, width))
        except Exception as e:
            logger.warning("wallpaper load failed: %s — %s", f.name, e)
    _wallpaper_cache = entries
    _wallpaper_dir_mtime = current_mtime
    logger.info("wallpaper cache refreshed: %d images loaded", len(entries))
    return entries

# ------------------------------------------------------------------ #
#  Data helpers                                                        #
# ------------------------------------------------------------------ #

def _ts_to_str(ts: float) -> str:
    if not ts:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
    except Exception:
        return str(ts)


def _login_label(c: dict) -> str:
    stage = c.get("login_stage", "")
    method = c.get("login_method", "")
    stage_map = {
        "logged_in": "已登录",
        "qr_waiting": "待扫码",
        "offline": "离线",
        "initializing": "初始化",
    }
    label = stage_map.get(stage, stage or "未知")
    method_map = {"sdk_ws": "SDK-WS", "filesystem": "文件系统"}
    method_label = method_map.get(method, method or "")
    return f"{label} / {method_label}" if method_label else label


# ------------------------------------------------------------------ #
#  HTML card builder                                                   #
# ------------------------------------------------------------------ #

def _build_card(c: dict, rank: int) -> str:
    online: bool = bool(c.get("bot_online", False))
    status: str = str(c.get("status", "unknown")).lower()

    # 状态判定
    if not online:
        state = "offline"
        badge_text = "OFFLINE"
    elif status == "paused":
        state = "paused"
        badge_text = "PAUSED"
    else:
        state = "online"
        badge_text = "ONLINE"

    name        = _html(c.get("name", "—"))
    uin         = _html(c.get("uin", ""))
    heartbeat   = _ts_to_str(c.get("bot_heartbeat_ts", 0))
    login_info  = _html(_login_label(c))
    bot_avatar  = _html(c.get("bot_avatar", ""))

    uin_display = uin or "—"

    if bot_avatar:
        # 有头像：img 铺满全卡，onerror 时隐藏图片（灰色底透出）
        bg_inner = f'<img src="{bot_avatar}" alt="avatar" onerror="this.style.display=\'none\'">'
        bg_class = "card-bg"
    else:
        # 无头像：纯灰色背景，简洁不突兀
        bg_inner = ""
        bg_class = "card-bg solid-grey"

    return (
        f'<div class="card">'
        f'<div class="{bg_class}">{bg_inner}</div>'
        f'<div class="card-hero">'
        f'<span class="live-badge {state}">{badge_text}</span>'
        f'</div>'
        f'<div class="card-body">'
        f'<div class="inst-name">{name}</div>'
        f'<div class="inst-uin">QQ: <span>{uin_display}</span></div>'
        f'<div class="meta-row">'
        f'<div class="meta-item"><span class="val">{login_info}</span></div>'
        f'<div class="meta-item"><span class="val">{heartbeat}</span></div>'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def _get_template() -> str:
    """读取模板文件，使用 mtime 缓存避免重复磁盘 IO。"""
    global _template_cache, _template_mtime
    try:
        current_mtime = _TEMPLATE_PATH.stat().st_mtime
    except OSError:
        if _template_cache:
            return _template_cache
        raise
    if _template_cache and current_mtime == _template_mtime:
        return _template_cache
    _template_cache = _TEMPLATE_PATH.read_text(encoding="utf-8")
    _template_mtime = current_mtime
    return _template_cache


def _render_html(containers: list[dict]) -> tuple[str, int]:
    """Fill template placeholders and return (final HTML, body_width).

    body 宽度由壁纸图片的实际像素宽度决定；无壁纸时回退 _DEFAULT_BODY_W。
    卡片使用 flex: 1 1 240px 自然按宽度弹性填充，一行放几张由壁纸宽度自动决定。
    """
    template = _get_template()
    total = len(containers)
    online = sum(1 for c in containers if c.get("bot_online"))
    offline = total - online
    # 面板壁纸（随机选一张铺满整个面板背景，同时取其像素宽度作为 body 宽度）
    wallpapers = _load_wallpapers()
    if wallpapers:
        wp_uri, body_width = random.choice(wallpapers)
        panel_wp = f'<div class="panel-wallpaper"><img src="{wp_uri}" alt=""></div>'
    else:
        panel_wp = ""
        body_width = _DEFAULT_BODY_W
    cards_html = "".join(
        _build_card(c, i + 1)
        for i, c in enumerate(containers)
    )
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = (
        template
        .replace("__BODY_WIDTH__", str(body_width))
        .replace("__PANEL_WALLPAPER__", panel_wp)
        .replace("__GENERATED_AT__", now_str)
        .replace("__TOTAL__", str(total))
        .replace("__ONLINE__", str(online))
        .replace("__OFFLINE__", str(offline))
        .replace("__CARDS__", cards_html)
    )
    return html, body_width
async def render_bindings(mapping: dict) -> bytes | str:
    """渲染昵称绑定对照图。如果渲染失败，返回纯文本作为回退。"""
    if not mapping:
        return "当前没有任何实例与用户的绑定对照记录。"

    global _bindings_template_cache, _bindings_template_mtime
    try:
        current_mtime = os.path.getmtime(_BINDINGS_TEMPLATE_PATH)
        if _bindings_template_cache is None or current_mtime > _bindings_template_mtime:
            with open(_BINDINGS_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                _bindings_template_cache = f.read()
            _bindings_template_mtime = current_mtime
        template = _bindings_template_cache
    except Exception as e:
        logger.error("Failed to read bindings.html: %s", e)
        return _fallback_bindings_text(mapping)

    # 构建行数据
    rows_html = ""
    for uid, data in mapping.items():
        safe_uid = _html(uid)
        nickname = _html(data.get("nickname") or "未设置")
        instances = data.get("instances") or []
        inst_str = _html("、".join(str(item) for item in instances) if instances else "（暂无实例）")
        rows_html += f'''
        <div class="row">
            <div class="col uid">{safe_uid}</div>
            <div class="col nick">{nickname}</div>
            <div class="col inst">{inst_str}</div>
        </div>
        '''

    html_content = template.replace("__ROWS__", rows_html)

    browser = await _ensure_browser()
    if browser is None:
        return _fallback_bindings_text(mapping)

    try:
        page = await browser.new_page()
        # 由于我们只需要截取对应区域，设置一个默认大小
        await page.set_viewport_size({"width": 800, "height": 100})
        await page.set_content(html_content, wait_until="networkidle")

        # 找到主体容器截图
        container = await page.query_selector(".container")
        if not container:
            await page.close()
            return _fallback_bindings_text(mapping)

        screenshot_bytes = await container.screenshot(type="jpeg", quality=90)
        await page.close()
        return screenshot_bytes

    except Exception as e:
        logger.error("Failed to render bindings via playwright: %s", e, exc_info=True)
        return _fallback_bindings_text(mapping)


def _fallback_bindings_text(mapping: dict) -> str:
    """兜底文本渲染"""
    if not mapping:
        return "当前没有任何实例与用户的绑定对照记录。"

    lines = ["📝 当前实例绑定对照表："]
    for uid, data in mapping.items():
        nickname = data.get("nickname") or "未设置"
        instances = data.get("instances") or []
        inst_str = "、".join(instances) if instances else "（暂无实例）"
        lines.append(f"• 用户 {uid} ({nickname}) 绑定实例：{inst_str}")
    return "\n".join(lines)

# ------------------------------------------------------------------ #
#  Plain-text fallback                                                 #
# ------------------------------------------------------------------ #

def _plain_text(containers: list[dict]) -> str:
    """Always-available plain-text rendering."""
    total = len(containers)
    online = sum(1 for c in containers if c.get("bot_online"))
    lines = [
        f"📋 NapCat 实例列表  共{total}个 | 在线{online} / 离线{total - online}",
        "─" * 36,
    ]
    for c in containers:
        is_online = c.get("bot_online", False)
        status_icon = "🟢" if is_online else "🔴"
        uin = c.get("uin", "—")
        name = c.get("name", "—")
        heartbeat = _ts_to_str(c.get("bot_heartbeat_ts", 0))
        login_info = _login_label(c)
        lines.append(
            f"{status_icon} [{name}]  QQ: {uin}\n"
            f"   状态: {login_info}  | 心跳: {heartbeat}"
        )
    lines.append("─" * 36)
    return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Public entry                                                        #
# ------------------------------------------------------------------ #

async def render_instances(containers: list[dict]) -> Union[str, bytes]:
    """Return PNG bytes (playwright) or plain-text str (fallback)."""
    if not containers:
        return "当前没有任何实例。"
    html, body_width = _render_html(containers)
    logger.info("render_instances: %d 个实例, body_width=%dpx, 开始截图...", len(containers), body_width)
    png = await _screenshot_html(html, viewport_width=body_width)
    if png:
        logger.info("render_instances: 截图成功, %d bytes", len(png))
        return png
    logger.warning("render_instances: playwright 截图失败, 回退纯文本")
    return _plain_text(containers)

