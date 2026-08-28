from __future__ import annotations

import asyncio
import socket
from typing import Any

from aiohttp import ClientSession

from voice.core_server import PlanaTTSLoopbackServer


class _Service:
    def __init__(self) -> None:
        self.synthesis_calls = 0

    def status(self) -> dict[str, Any]:
        return {"ok": True, "transport": "test"}

    async def synthesize(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.synthesis_calls += 1
        return {
            "ok": True,
            "contract_version": payload.get("contract_version"),
            "audio_path": "test.wav",
        }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def check_core_loopback() -> None:
    service = _Service()
    server = PlanaTTSLoopbackServer(
        service,
        enabled=True,
        port=_free_port(),
        core_service_key="tts-test-key",
    )
    assert await server.start()
    base = f"http://127.0.0.1:{server.port}/plana_tts"
    try:
        async with ClientSession() as session:
            async with session.post(
                f"{base}/synthesize",
                json={"contract_version": "plana.voice.synthesis.v1"},
                headers={"X-Plana-Core-Key": "wrong"},
            ) as response:
                assert response.status == 401
            assert service.synthesis_calls == 0
            headers = {"X-Plana-Core-Key": "tts-test-key"}
            async with session.get(f"{base}/state", headers=headers) as response:
                assert response.status == 200
            async with session.post(
                f"{base}/synthesize",
                json={"contract_version": "plana.voice.synthesis.v1"},
                headers=headers,
            ) as response:
                assert response.status == 200
            assert service.synthesis_calls == 1
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(check_core_loopback())
    print("tts_core_loopback_check=ok")
