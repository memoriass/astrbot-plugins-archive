from __future__ import annotations

import base64
import io

import qrcode

from ..core.http import HttpClient
from .manager_response import error, ok


class AccountQrLoginService:
    async def start(self) -> dict:
        client = await HttpClient.get_client()
        try:
            res = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                timeout=8,
            )
            body = res.json()
            data = body.get("data") or {}
            url = str(data.get("url") or "")
            qrcode_key = str(data.get("qrcode_key") or "")
        except Exception as exc:
            return error(f"二维码获取失败: {exc}")

        if not url or not qrcode_key:
            return error("二维码获取失败。")

        return ok(
            {
                "qrcode_key": qrcode_key,
                "url": url,
                "image": qr_data_url(url),
                "status": "pending",
                "message": "请使用 B 站 App 扫码登录。",
            }
        )

    async def poll(self, payload: dict) -> dict:
        qrcode_key = str(payload.get("qrcode_key") or "").strip()
        if not qrcode_key:
            return error("qrcode_key 参数不能为空。")

        client = await HttpClient.get_client()
        try:
            res = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": qrcode_key},
                timeout=8,
            )
            data = (res.json().get("data") or {})
        except Exception as exc:
            return error(f"二维码状态检查失败: {exc}")

        try:
            code = int(data.get("code"))
        except (TypeError, ValueError):
            code = -1
        if code == 0:
            account = await save_qr_account(client, data, dict(res.cookies))
            return ok({"status": "success", "message": "登录成功。", "account": account})
        if code == 86038:
            return ok({"status": "expired", "message": "二维码已失效，请重新获取。"})
        if code == 86090:
            return ok({"status": "scanned", "message": "已扫码，请在 B 站 App 确认。"})
        return ok({"status": "pending", "message": "等待扫码确认。"})


async def save_qr_account(client, data: dict, cookies: dict) -> dict:
    uid = str(cookies.get("DedeUserID") or data.get("mid") or "")
    uname = str(data.get("uname") or "未知")
    face = str(data.get("face") or "")

    try:
        nav_res = await client.get(
            "https://api.bilibili.com/x/web-interface/nav",
            cookies=cookies,
            timeout=5,
        )
        nav_data = nav_res.json()
        if nav_data.get("code") == 0:
            nav = nav_data.get("data") or {}
            uid = str(nav.get("mid") or uid)
            uname = str(nav.get("uname") or uname)
            face = str(nav.get("face") or face)
    except Exception:
        pass

    await HttpClient.add_account(uid=uid, name=uname, face=face, cookies=cookies)
    return {"uid": uid, "name": uname, "face": face}


def qr_data_url(url: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
