import asyncio
import io
import time
from pathlib import Path

import qrcode

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..core.http import HttpClient
from ..rendering import RendererPort


class LoginHandler:
    def __init__(
        self,
        context: Context,
        temp_dir: Path,
        bg_dir: Path,
        renderer: RendererPort,
    ):
        self.context = context
        self.temp_dir = temp_dir
        self.bg_dir = bg_dir
        self.renderer = renderer

    async def handle_login(self, event: AstrMessageEvent):
        client = await HttpClient.get_client()
        try:
            res = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            )
            data = res.json()["data"]
            url, qrcode_key = data["url"], data["qrcode_key"]
        except Exception as e:
            yield event.plain_result(f"❌ 二维码获取失败: {e}")
            return

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")

        qr_path = self.temp_dir / f"qr_{int(time.time())}.png"
        with open(qr_path, "wb") as f:
            f.write(img_byte_arr.getvalue())

        yield event.chain_result(
            [
                Comp.Plain("请使用 B站 App 扫码登录：\n"),
                Comp.Image.fromFileSystem(str(qr_path.absolute())),
            ]
        )

        for _ in range(30):
            await asyncio.sleep(4)
            try:
                check_res = await client.get(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                    params={"qrcode_key": qrcode_key},
                )
                check_data = check_res.json()["data"]
                if check_data["code"] == 0:
                    new_cookies = dict(check_res.cookies)
                    uid = new_cookies.get("DedeUserID") or str(
                        check_data.get("mid", "")
                    )
                    try:
                        nav_res = await client.get(
                            "https://api.bilibili.com/x/web-interface/nav",
                            cookies=new_cookies,
                            timeout=5,
                        )
                        nav_data = nav_res.json()
                        if nav_data["code"] == 0:
                            n = nav_data["data"]
                            uid, uname, face = (
                                str(n.get("mid")),
                                n.get("uname"),
                                n.get("face"),
                            )
                        else:
                            uname, face = (
                                check_data.get("uname", "未知"),
                                check_data.get("face", ""),
                            )
                    except Exception:
                        uname, face = check_data.get("uname", "未知"), ""
                    await HttpClient.add_account(
                        uid=uid, name=uname, face=face, cookies=new_cookies
                    )
                    yield event.plain_result(
                        f"✅ 登录成功！已添加账号：{uname} (UID: {uid})"
                    )
                    return
                elif check_data["code"] == 86038:
                    yield event.plain_result("❌ 二维码已失效")
                    return
            except Exception as e:
                logger.error(f"Login QR poll failed: {e}")
        yield event.plain_result("⏳ 登录超时")

    async def handle_status(self, event: AstrMessageEvent):
        accounts = await HttpClient.get_accounts()
        if not accounts:
            yield event.plain_result("❌ 当前未登录任何账号")
            return
        current_idx = HttpClient._current_account_index
        display_list = []
        for i, acc in enumerate(accounts):
            is_valid = acc.get("valid", True)
            status_code = acc.get("status_code")
            cooldown_until = int(acc.get("cooldown_until") or 0)

            status_label = None
            status_class = "badge-risk"

            if cooldown_until:
                status_label = "风控冷却中"
            elif status_code:
                status_label = f"Code {status_code}"
                if str(status_code) == "412":
                    status_label = "风控 412"
                elif str(status_code) == "352":
                    status_label = "拦截 352"
            elif not is_valid:
                status_label = "失效"

            display_list.append(
                {
                    "uid": acc.get("uid"),
                    "username": acc.get("name"),
                    "face": acc.get("face")
                    or "http://i0.hdslb.com/bfs/face/member/noface.jpg",
                    "status_label": status_label,
                    "status_class": status_class,
                    "is_active_account": (i == current_idx),
                    "has_live": False,
                    "has_dynamic": False,
                }
            )

        try:
            img_bytes = await self.renderer.render(
                "sub_list.html.jinja",
                {
                    "subs": display_list,
                    "page_title": "登录账号状态",
                },
                viewport={"width": 1000, "height": 800},
                selector=".card-board",
            )
            yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
        except Exception as e:
            logger.error(f"Status render failed: {e}")
            yield event.plain_result("❌ 状态渲染失败")
