from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import random
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.html_renderer import (  # noqa: E402
    BrowserManager,
    HtmlRenderer,
)
from utils.resource import get_template_path  # noqa: E402
from utils.timezone import format_bilibili_time  # noqa: E402


def image_data_uri(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{payload}"


def generated_image_uri(
    rng: random.Random,
    label: str,
    size: tuple[int, int] = (960, 540),
) -> str:
    palette = [
        ((251, 114, 153), (0, 161, 214), (255, 255, 255)),
        ((67, 160, 71), (255, 193, 7), (255, 255, 255)),
        ((33, 150, 243), (156, 39, 176), (255, 255, 255)),
        ((255, 112, 67), (38, 166, 154), (255, 255, 255)),
    ]
    first, second, text = rng.choice(palette)
    width, height = size
    img = Image.new("RGB", size, first)
    px = img.load()
    for y in range(height):
        ratio_y = y / max(height - 1, 1)
        for x in range(width):
            ratio = (x / max(width - 1, 1) + ratio_y) / 2
            px[x, y] = tuple(
                int(first[i] * (1 - ratio) + second[i] * ratio) for i in range(3)
            )

    draw = ImageDraw.Draw(img)
    for _ in range(18):
        x0 = rng.randint(-80, width - 80)
        y0 = rng.randint(-80, height - 80)
        radius = rng.randint(60, 180)
        color = tuple(min(255, c + rng.randint(15, 55)) for c in rng.choice([first, second]))
        draw.ellipse((x0, y0, x0 + radius, y0 + radius), fill=color)

    draw.rounded_rectangle(
        (32, height - 112, width - 32, height - 32),
        radius=18,
        fill=(0, 0, 0),
        outline=(255, 255, 255),
        width=2,
    )
    draw.text((56, height - 84), label[:48], fill=text)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def https_url(url: str | None) -> str:
    if not url:
        return ""
    return "https://" + url[7:] if url.startswith("http://") else url


def fetch_bilibili_popular(limit: int = 8) -> list[dict]:
    url = f"https://api.bilibili.com/x/web-interface/popular?ps={limit}&pn=1"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("code") == 0:
            return payload.get("data", {}).get("list", [])[:limit]
    except Exception as exc:
        print(f"bilibili_fetch_failed={exc}")
    return []


def duration_text(seconds: int | None) -> str:
    seconds = int(seconds or 0)
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour}:{minute:02d}:{second:02d}"
    return f"{minute}:{second:02d}"


def count_text(value: int | None) -> str:
    value = int(value or 0)
    if value >= 10000:
        return f"{value / 10000:.1f}万"
    return str(value)


def time_text(timestamp: int | None) -> str:
    if not timestamp:
        return "2026-06-14 21:30"
    return format_bilibili_time(timestamp, "%Y-%m-%d %H:%M")


def item_url(item: dict | None) -> str:
    if not item:
        return "https://www.bilibili.com/"
    if item.get("short_link_v2"):
        return item["short_link_v2"]
    if item.get("bvid"):
        return f"https://www.bilibili.com/video/{item['bvid']}"
    return "https://www.bilibili.com/"


def sample_post(rng: random.Random, avatar: str, cover: str, images: list[str]):
    return SimpleNamespace(
        platform="bilibili-dynamic",
        content=(
            "新动态发布：整理了最近一次直播里提到的工具链、模板渲染和订阅推送优化，"
            "顺手补了一组截图给大家对比。"
        ),
        title=rng.choice(
            [
                "Bilibili 动态推送模板预览",
                "多图动态：模板透明化与卡片布局",
                "UP 主更新：本周开发记录",
            ]
        ),
        timestamp=int(time.time()),
        url="https://www.bilibili.com/opus/sample",
        nickname=rng.choice(["山城记录员", "模板调试研究所", "Bili 工具箱"]),
        images=images,
        id=f"opus-{rng.randint(100000, 999999)}",
        avatar=avatar,
        repost=None,
        category=1,
        type="DYNAMIC_TYPE_DRAW",
    )


def live_post(rng: random.Random, avatar: str, cover: str):
    return SimpleNamespace(
        platform="bilibili-live",
        content="直播间已开播，今晚测试插件模板预览、订阅列表透明背景和多账号状态卡片。",
        title=rng.choice(["正在直播：插件模板联调", "Bilibili 推送卡片实机预览"]),
        timestamp=int(time.time()),
        url="https://live.bilibili.com/123456",
        nickname=rng.choice(["直播调试台", "代码夜航船", "B站工具间"]),
        images=[cover],
        id=f"live-{rng.randint(100000, 999999)}",
        avatar=avatar,
        repost=None,
        category=2,
        type="LIVE",
    )


def build_preview_jobs(rng: random.Random, bili_items: list[dict]):
    template_dir = get_template_path()
    item_a = bili_items[0] if len(bili_items) > 0 else None
    item_b = bili_items[1] if len(bili_items) > 1 else None
    parser_item = bili_items[2] if len(bili_items) > 2 else item_a
    avatar_a = https_url((item_a or {}).get("owner", {}).get("face")) or image_data_uri(
        template_dir / "bison_logo.png"
    )
    avatar_b = https_url((item_b or {}).get("owner", {}).get("face")) or image_data_uri(
        template_dir / "ceobecanteen_logo.png"
    )
    covers = [https_url(item.get("pic")) for item in bili_items if item.get("pic")]
    generated_labels = [
        "BILIBILI OPUS SAMPLE",
        "LIVE ROOM COVER",
        "VIDEO BV SAMPLE",
        "DYNAMIC IMAGE 01",
        "DYNAMIC IMAGE 02",
        "DYNAMIC IMAGE 03",
    ]
    while len(covers) < 6:
        label = generated_labels[len(covers) % len(generated_labels)]
        size = (720, 720) if len(covers) >= 3 else (960, 540)
        covers.append(generated_image_uri(rng, label, size))

    dynamic = sample_post(rng, avatar_a, covers[0], covers[3:])
    if item_a:
        owner = item_a.get("owner", {})
        dynamic.content = item_a.get("desc") or item_a.get("dynamic") or dynamic.content
        dynamic.title = item_a.get("title") or dynamic.title
        dynamic.timestamp = int(item_a.get("pubdate") or dynamic.timestamp)
        dynamic.url = item_url(item_a)
        dynamic.nickname = owner.get("name") or dynamic.nickname
        dynamic.id = item_a.get("bvid") or str(item_a.get("aid") or dynamic.id)
    live = live_post(rng, avatar_b, covers[1])
    if item_b:
        owner = item_b.get("owner", {})
        live.nickname = owner.get("name") or live.nickname
        live.title = f"直播预览：{item_b.get('title') or live.title}"
    parser_stat = (parser_item or {}).get("stat", {})

    subs = [
        {
            "uid": str((item_a or {}).get("owner", {}).get("mid") or "946974"),
            "username": (item_a or {}).get("owner", {}).get("name") or "哔哩哔哩样例UP",
            "face": avatar_a,
            "has_dynamic": True,
            "has_live": True,
            "is_live": True,
        },
        {
            "uid": str((item_b or {}).get("owner", {}).get("mid") or "354665623"),
            "username": (item_b or {}).get("owner", {}).get("name") or "模板调试研究所",
            "face": avatar_b,
            "has_dynamic": True,
            "has_live": False,
            "is_live": False,
        },
        {
            "uid": "204970876",
            "username": "直播状态观察员",
            "face": avatar_a,
            "has_dynamic": False,
            "has_live": True,
            "is_live": False,
        },
    ]
    login_accounts = [
        {
            "uid": "100001",
            "username": "主推送账号",
            "face": avatar_a,
            "status_label": None,
            "status_class": "badge-risk",
            "is_active_account": True,
            "has_live": False,
            "has_dynamic": False,
        },
        {
            "uid": "100002",
            "username": "备用账号",
            "face": avatar_b,
            "status_label": "风控 412",
            "status_class": "badge-warn",
            "is_active_account": False,
            "has_live": False,
            "has_dynamic": False,
        },
    ]
    workflow_candidates = [
        {
            "uid": sub["uid"],
            "username": sub["username"],
            "face": sub["face"],
            "has_dynamic": True,
            "has_live": True,
            "is_live": False,
        }
        for sub in subs
    ]

    return [
        {
            "name": "parser_bili",
            "template": "parser_bili.html.jinja",
            "data": {
                "avatar": https_url((parser_item or {}).get("owner", {}).get("face"))
                or avatar_a,
                "nickname": (parser_item or {}).get("owner", {}).get("name")
                or "模板调试研究所",
                "pub_time": time_text((parser_item or {}).get("pubdate")),
                "title": (parser_item or {}).get("title")
                or "插件模板预览：透明背景与卡片截图测试",
                "cover": https_url((parser_item or {}).get("pic")) or covers[2],
                "duration": duration_text((parser_item or {}).get("duration")),
                "description": (parser_item or {}).get("desc")
                or "这是一条用于本地预览的 Bilibili 链接解析数据，包含封面、作者、统计和简介。",
                "stats": {
                    "view": count_text(parser_stat.get("view")),
                    "like": count_text(parser_stat.get("like")),
                    "coin": count_text(parser_stat.get("coin")),
                },
            },
            "viewport": {"width": 700, "height": 980},
            "selector": ".card",
        },
        {
            "name": "sub_add_dynamic",
            "template": "sub_add.html.jinja",
            "data": {
                "face": avatar_a,
                "username": (item_a or {}).get("owner", {}).get("name")
                or "哔哩哔哩样例UP",
                "uid": str((item_a or {}).get("owner", {}).get("mid") or "946974"),
                "sub_type": "dynamic",
                "action": "ADD SUB",
            },
            "viewport": {"width": 420, "height": 420},
            "selector": ".card",
        },
        {
            "name": "sub_add_live",
            "template": "sub_add.html.jinja",
            "data": {
                "face": avatar_b,
                "username": (item_b or {}).get("owner", {}).get("name")
                or "直播状态观察员",
                "uid": str((item_b or {}).get("owner", {}).get("mid") or "204970876"),
                "sub_type": "live",
                "action": "ADD LIVE",
            },
            "viewport": {"width": 420, "height": 420},
            "selector": ".card",
        },
        {
            "name": "sub_list_subscriptions",
            "template": "sub_list.html.jinja",
            "data": {"page_title": "订阅列表", "subs": subs},
            "viewport": {"width": 1000, "height": 800},
            "selector": ".card-board",
        },
        {
            "name": "sub_list_login_accounts",
            "template": "sub_list.html.jinja",
            "data": {"page_title": "登录账号状态", "subs": login_accounts},
            "viewport": {"width": 1000, "height": 620},
            "selector": ".card-board",
        },
        {
            "name": "workflow_candidates",
            "template": "workflow_candidates.html.jinja",
            "data": {
                "page_title": "请选择要订阅的 UP: Bilibili",
                "note": "引用这条消息回复序号即可选择候选；确认前不会写入订阅。",
                "candidates": workflow_candidates,
            },
            "viewport": {"width": 1000, "height": 860},
            "selector": ".workflow-board",
        },
        {
            "name": "workflow_confirm",
            "template": "workflow_confirm.html.jinja",
            "data": {
                "face": avatar_a,
                "username": (item_a or {}).get("owner", {}).get("name")
                or "哔哩哔哩样例UP",
                "uid": str((item_a or {}).get("owner", {}).get("mid") or "946974"),
                "sub_type": "dynamic",
                "action_label": "待确认",
                "title": "确认订阅动态吗？",
                "summary": "确认后会写入当前会话；取消则不会改动订阅。",
                "confirm_text": "引用回复 确认",
                "cancel_text": "引用回复 取消",
            },
            "viewport": {"width": 560, "height": 620},
            "selector": ".workflow-confirm",
        },
        {
            "name": "movie_card_live",
            "template": "movie_card.html.jinja",
            "data": {
                "post": live,
                "date_str": "2026-06-14 21:30:00",
                "cover": covers[1],
            },
            "viewport": {"width": 700, "height": 900},
            "selector": ".movie-card",
        },
        {
            "name": "dynamic_movie_card",
            "template": "dynamic_movie_card.html.jinja",
            "data": {
                "post": dynamic,
                "date_str": "2026-06-14 21:30:00",
                "cover": covers[0],
            },
            "viewport": {"width": 700, "height": 1100},
            "selector": ".movie-card",
        },
    ]


async def render_previews(output_dir: Path, seed: int) -> list[Path]:
    rng = random.Random(seed)
    renderer = HtmlRenderer(get_template_path())
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    bili_items = fetch_bilibili_popular()
    print(f"bilibili_items={len(bili_items)}")
    try:
        for job in build_preview_jobs(rng, bili_items):
            image = await renderer.render(
                job["template"],
                job["data"],
                viewport=job["viewport"],
                selector=job["selector"],
            )
            path = output_dir / f"{job['name']}.png"
            path.write_bytes(image)
            rendered.append(path)
            print(f"rendered {path}")
    finally:
        await BrowserManager.close()
    return rendered


def make_contact_sheet(paths: list[Path], output_path: Path) -> None:
    thumbs = []
    for path in paths:
        img = Image.open(path).convert("RGBA")
        img.thumbnail((360, 260), Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (400, 320), (246, 248, 250, 255))
        x = (400 - img.width) // 2
        y = 34 + (248 - img.height) // 2
        tile.alpha_composite(img, (x, y))
        draw = ImageDraw.Draw(tile)
        draw.text((16, 12), path.stem, fill=(31, 41, 55, 255))
        thumbs.append(tile)

    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * 400, rows * 320), (255, 255, 255, 255))
    for index, tile in enumerate(thumbs):
        x = index % cols * 400
        y = index // cols * 320
        sheet.alpha_composite(tile, (x, y))
    sheet.save(output_path)


def parse_args():
    parser = argparse.ArgumentParser(description="Render local previews for HTML templates.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "template_previews"),
        help="Directory for generated preview PNG files.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(time.time()),
        help="Random seed for sample data and generated covers.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    print(f"seed={args.seed}")
    paths = asyncio.run(render_previews(output_dir, args.seed))
    sheet = output_dir / "_contact_sheet.png"
    make_contact_sheet(paths, sheet)
    print(f"rendered {sheet}")


if __name__ == "__main__":
    main()
