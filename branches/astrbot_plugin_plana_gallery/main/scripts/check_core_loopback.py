from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path
from typing import Any

from aiohttp import ClientSession

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.chat_server import GalleryLoopbackServer


class _Service:
    def __init__(self) -> None:
        self.feedback_calls = 0

    def status(self) -> dict[str, Any]:
        return {"ok": True, "transport": "test"}

    def candidates(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "contract_version": payload.get("contract_version"),
            "candidates": [],
        }

    def feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.feedback_calls += 1
        return {"ok": True, "event_id": payload.get("event_id")}

    def resolve(self, asset_ref: str) -> dict[str, Any]:
        return {"ok": asset_ref == "gallery:test", "asset_ref": asset_ref}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def check_core_loopback() -> None:
    service = _Service()
    server = GalleryLoopbackServer(
        service,
        enabled=True,
        port=_free_port(),
        core_service_key="gallery-test-key",
    )
    assert await server.start()
    base = f"http://127.0.0.1:{server.port}"
    try:
        async with ClientSession() as session:
            async with session.post(
                f"{base}/plana_gallery/api/chat/feedback",
                json={"event_id": "blocked"},
                headers={"X-Plana-Core-Key": "wrong"},
            ) as response:
                assert response.status == 401
            assert service.feedback_calls == 0
            headers = {"X-Plana-Core-Key": "gallery-test-key"}
            async with session.post(
                f"{base}/plana_gallery/api/chat/candidates",
                json={"contract_version": "plana.gallery.candidates.v1"},
                headers=headers,
            ) as response:
                assert response.status == 200
                assert (await response.json())["ok"] is True
            async with session.get(
                f"{base}/plana_gallery/api/chat/resolve",
                params={"asset_ref": "gallery:test"},
                headers=headers,
            ) as response:
                assert response.status == 200
            async with session.post(
                f"{base}/plana_gallery/api/chat/feedback",
                json={"event_id": "accepted"},
                headers=headers,
            ) as response:
                assert response.status == 200
            assert service.feedback_calls == 1
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(check_core_loopback())
    print("gallery_core_loopback_check=ok")
