from astrbot.api import logger
from astrbot.api.all import Image

from .client import NCQQClient


async def do_check_login_status(client: NCQQClient, instance_name: str) -> dict:
    """Call POST /api/containers/{name}/refresh-login.

    New API response: {status:"ok", logged_in:bool, uin:"", nickname:"", method:""}
    On error returns: {status:"error", logged_in:False, msg:"..."}
    """
    try:
        res = await client.make_request(
            "POST", f"/api/containers/{instance_name}/refresh-login"
        )
        return res if isinstance(res, dict) else {"status": "ok", "logged_in": False}
    except Exception as e:
        logger.warning("刷新登录状态 %s 失败: %s", instance_name, e)
        return {"status": "error", "logged_in": False, "msg": "登录状态查询失败，请稍后重试。"}


def is_qrcode_available_status(status_payload: dict) -> tuple[bool, str]:
    """Determine whether the instance is eligible for QR code retrieval.

    New API refresh-login returns {logged_in:bool, ...}.
    - logged_in=True  → already online, QR not needed
    - status=="error" → interface failure, QR not available
    - otherwise       → offline/waiting, QR available
    """
    if status_payload.get("status") == "error":
        msg = str(status_payload.get("msg", "接口故障"))
        return False, msg
    logged_in = status_payload.get("logged_in", False)
    if logged_in:
        uin = status_payload.get("uin", "")
        nickname = status_payload.get("nickname", "")
        label = f"{nickname}({uin})" if uin else "已登录"
        return False, f"实例当前在线（{label}），无需扫码。"
    return True, ""



# 二维码有效期阈值：剩余秒数低于此值时视为"即将过期"，触发自动重取
_QR_EXPIRY_THRESHOLD = 15


async def do_get_qrcode(client: NCQQClient, instance_name: str) -> list:
    """Fetch QR code for an instance. Returns a list of str / Image items.

    Backend GET /api/containers/{name}/qrcode response variants:
      {status:"logged_in", uin:"..."}
      {status:"waiting"}                          ← 容器未就绪 or 二维码文件已过期
      {status:"ok", url:"data:image/png;base64,...", type:"file",
       expires_in:N, expires_at:T, generated_at:T}
      {status:"ok", url:"https://...", type:"log"}  ← 从日志提取，无 expires_in

    当 expires_in 存在时：
      - expires_in > _QR_EXPIRY_THRESHOLD → 正常展示，附带有效期提示
      - expires_in <= _QR_EXPIRY_THRESHOLD → 返回 sentinel 触发调用方 sleep + retry

    Sentinel 格式（list 首项）：
      "__qr_soon__:{expires_in}"   二维码即将过期，需等待后重取
    """
    try:
        res = await client.make_request(
            "GET", f"/api/containers/{instance_name}/qrcode"
        )
        if not isinstance(res, dict):
            return ["二维码接口返回异常，暂时无法解析，请稍后重试。"]

        status = str(res.get("status", "")).lower().strip()

        if status == "logged_in":
            uin = res.get("uin", "")
            return [f"实例已登录（账号：{uin}），无需扫码。"]

        if status == "waiting":
            return ["二维码暂时不可用，可能正在生成或上一张已过期，请稍后重试。"]

        if status == "ok":
            url: str = res.get("url", "")
            expires_in = res.get("expires_in")  # 仅 type=="file" 时存在

            if url.startswith("data:image"):
                # Inline base64 image (type=="file")
                b64_data = url.split(",", 1)[1] if "," in url else url

                if expires_in is not None:
                    secs = int(expires_in)
                    if secs <= _QR_EXPIRY_THRESHOLD:
                        # 即将过期：返回 sentinel，让调用方等待后重取
                        tip = (
                            f"当前二维码仅剩约 {secs} 秒有效，"
                            f"稍等 {secs + 2} 秒后将自动重新获取…"
                        )
                        return [f"__qr_soon__:{secs + 2}", tip]
                    # 有效期充足：展示并告知剩余时间
                    return [
                        Image.fromBase64(b64_data),
                        f"登录二维码已就绪，请在 {secs} 秒内用手机 QQ 扫码登录。",
                    ]

                # type=="file" 但无 expires_in（兼容旧版后端）
                return [
                    Image.fromBase64(b64_data),
                    "登录二维码已就绪，请尽快用手机 QQ 扫码登录。",
                ]

            if url.startswith("http"):
                # External URL extracted from container logs (type=="log")
                return [
                    Image.fromURL(url),
                    "从容器日志中提取到二维码地址，请尽快扫码登录。",
                ]

            return ["二维码已生成，但当前返回格式暂不支持直接展示，请联系管理员检查后端配置。"]

        return ["当前无法获取二维码，请稍后重试。"]
    except Exception as e:
        logger.warning("获取二维码 %s 失败: %s", instance_name, e)
        return ["接口调用异常，请稍后重试。"]
