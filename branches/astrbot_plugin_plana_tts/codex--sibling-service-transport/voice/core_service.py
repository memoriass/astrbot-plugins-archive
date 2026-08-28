from __future__ import annotations

from typing import Any


class PlanaTTSCoreService:
    """Controlled in-process synthesis surface for Plana Core."""

    def __init__(self, plugin: Any, contract_version: str) -> None:
        self.plugin = plugin
        self.contract_version = contract_version

    async def synthesize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if str(payload.get("contract_version") or "") != self.contract_version:
            return {
                "ok": False,
                "error": "contract_version_mismatch",
                "contract_version": self.contract_version,
            }
        content = " ".join(str(payload.get("text") or "").split())
        error = self.plugin._validation_error(
            content,
            str(payload.get("message_type") or ""),
        )
        if error:
            return self.plugin._error_payload(error)
        return await self.plugin._synthesize_audio_limited(
            content,
            str(payload.get("unified_msg_origin") or ""),
        )

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "contract_version": self.contract_version,
            "status": self.plugin._status_payload(),
            "transport": "in_process",
        }
