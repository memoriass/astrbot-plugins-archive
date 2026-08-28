from pathlib import Path

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..rendering import RendererPort
from .subscription_editor import SubscriptionEditor
from .subscription_list import SubscriptionListPresenter


class SubscriptionHandler:
    def __init__(self, context: Context, db, bg_dir: Path, renderer: RendererPort):
        self.context = context
        self.editor = SubscriptionEditor(db, renderer)
        self.list_presenter = SubscriptionListPresenter(db, bg_dir, renderer)

    def _get_target_id(self, event: AstrMessageEvent):
        return event.unified_msg_origin

    async def add_subscription(self, event: AstrMessageEvent, uid: str, parser):
        async for ret in self.editor.add(
            event,
            self._get_target_id(event),
            uid,
            parser,
            "dynamic",
        ):
            yield ret

    async def add_live_subscription(self, event: AstrMessageEvent, uid: str, parser):
        async for ret in self.editor.add(
            event,
            self._get_target_id(event),
            uid,
            parser,
            "live",
        ):
            yield ret

    async def remove_subscription(
        self, event: AstrMessageEvent, uid: str, sub_type: str, parser
    ):
        async for ret in self.editor.remove(
            event,
            self._get_target_id(event),
            uid,
            sub_type,
            parser,
        ):
            yield ret

    async def list_subscriptions(self, event: AstrMessageEvent, scheduler):
        async for ret in self.list_presenter.show(
            event,
            self._get_target_id(event),
            scheduler,
        ):
            yield ret
