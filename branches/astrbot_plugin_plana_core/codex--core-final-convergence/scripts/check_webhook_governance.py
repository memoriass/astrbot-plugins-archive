from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugin.db import Database
from plugin.webhook_governance import WEBHOOK_PLUGIN_NAME, WebhookGovernanceService


class Companion:
    def __init__(self, core_service_key: str) -> None:
        self.replayed: list[str] = []
        self.core_service_key = core_service_key

    def _authorized(self, core_token: str) -> bool:
        return core_token == self.core_service_key

    def status(self, *, core_token: str = "") -> dict:
        if not self._authorized(core_token):
            return {"ok": False, "error": "core_service_unauthorized"}
        return {"ok": True, "contract_version": "plana.webhook.event.v1"}

    def sources(self, *, core_token: str = "") -> dict:
        if not self._authorized(core_token):
            return {"ok": False, "error": "core_service_unauthorized", "sources": []}
        return {
            "ok": True,
            "sources": [
                {"source": "media", "routes": ["/media-webhook"], "template": "media_movie_modern.html"},
                {"source": "game", "routes": ["/game-webhook"], "template": "game_modern.html"},
                {"source": "common", "routes": ["/webhook"], "template": "common_blog.html"},
            ],
        }

    def recent_events(self, limit: int = 50, *, core_token: str = "") -> dict:
        if not self._authorized(core_token):
            return {"ok": False, "error": "core_service_unauthorized", "events": []}
        return {"ok": True, "events": []}

    async def replay(self, event_id: str, *, core_token: str = "") -> dict:
        if not self._authorized(core_token):
            return {"ok": False, "error": "core_service_unauthorized"}
        self.replayed.append(event_id)
        return {"ok": True, "event_id": event_id, "status": "replay_queued"}


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        core_service_key = "webhook-test-key"
        companion = Companion(core_service_key)
        runtime = SimpleNamespace(
            storage=SimpleNamespace(db=Database(Path(tmp) / "core.db")),
            sibling_services={WEBHOOK_PLUGIN_NAME: companion},
            astr_context=None,
            config={"plana_core_service_key": core_service_key},
        )
        service = WebhookGovernanceService(runtime)
        service.initialize()
        event = {
            "contract_version": "plana.webhook.event.v1",
            "event_id": "webhook-media-1",
            "source": "media",
            "event_type": "media.webhook",
            "dedupe_key": "abc",
            "payload_ref": "sha256:abc",
            "summary": "Movie",
            "target": "123",
            "template": "media_movie_modern.html",
        }
        try:
            service.evaluate_event(event, core_token="wrong")
        except PermissionError as exc:
            assert str(exc) == "core_service_unauthorized"
        else:
            raise AssertionError("wrong Core token must be rejected")
        assert service.evaluate_event(event, core_token=core_service_key)["action"] == "deliver"
        duplicate = service.evaluate_event(
            {**event, "event_id": "webhook-media-2"},
            core_token=core_service_key,
        )
        assert duplicate["reason"] == "duplicate_event"
        assert service.update_policy("media", {"enabled": False}, actor="check")["ok"]
        service.record_delivery(
            "webhook-media-1",
            "failed",
            core_token=core_service_key,
            error="send_failed",
        )
        assert (await service.replay("webhook-media-1"))["ok"]
        assert companion.replayed == ["webhook-media-1"]
        assert service.events(10)["events"][0]["delivery_status"] == "replay_requested"
    print("webhook_governance=ok")


if __name__ == "__main__":
    asyncio.run(main())
