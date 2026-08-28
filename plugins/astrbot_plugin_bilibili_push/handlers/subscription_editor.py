import astrbot.api.message_components as Comp
from astrbot.api import logger

from ..database.db_manager import Subscription
from ..rendering import RendererPort


class SubscriptionEditor:
    def __init__(self, db, renderer: RendererPort):
        self.db = db
        self.renderer = renderer

    async def add(self, event, target_id: str, uid: str, parser, sub_type: str):
        try:
            user_info = await parser.get_user_info(uid)
            if not user_info:
                yield event.plain_result(f"❌ 无法获取 UP 主信息: {uid}")
                return

            sub = Subscription(
                uid=uid,
                username=user_info["username"],
                sub_type=sub_type,
                categories=self._default_categories(sub_type),
                tags=[],
                target_id=target_id,
                enabled=True,
            )

            if self.db.add_subscription(sub):
                img_bytes = await self._render_change_card(
                    user_info["username"],
                    user_info["face"],
                    uid,
                    sub_type,
                    "ADDED",
                )
                label = "动态" if sub_type == "dynamic" else "直播"
                yield event.chain_result(
                    [
                        Comp.Plain(
                            f"✅ 已添加{label}订阅: {user_info['username']} ({uid})"
                        ),
                        Comp.Image.fromBytes(img_bytes),
                    ]
                )
            else:
                yield event.plain_result("⚠️ 订阅已存在")
        except Exception as exc:
            logger.error(f"Add {sub_type} sub failed: {exc}")
            yield event.plain_result(f"❌ 内部错误: {exc}")

    async def remove(self, event, target_id: str, uid: str, sub_type: str, parser):
        user_info = await parser.get_user_info(uid)
        username, face = (
            (user_info["username"], user_info["face"]) if user_info else (uid, "")
        )

        if self.db.remove_subscription(uid, sub_type, target_id):
            img_bytes = await self._render_change_card(
                username,
                face,
                uid,
                sub_type,
                "REMOVED",
            )
            yield event.chain_result(
                [
                    Comp.Plain(f"🗑️ 已取消{sub_type}订阅: {username} ({uid})"),
                    Comp.Image.fromBytes(img_bytes),
                ]
            )
        else:
            yield event.plain_result(f"❌ {sub_type}订阅不存在: {uid}")

    def _default_categories(self, sub_type: str) -> list[int]:
        return [1, 2, 3, 4, 5, 6] if sub_type == "dynamic" else [1, 2, 3]

    async def _render_change_card(
        self,
        username: str,
        face: str,
        uid: str,
        sub_type: str,
        action: str,
    ) -> bytes:
        return await self.renderer.render(
            "sub_add.html.jinja",
            {
                "username": username,
                "face": face,
                "uid": uid,
                "sub_type": sub_type,
                "action": action,
            },
            viewport={"width": 400, "height": 400},
            selector=".card",
        )
