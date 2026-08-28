from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


class CapabilityError(RuntimeError):
    pass


CapabilityHandler = Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ActionEnvelope:
    service_ref: str
    capability: str
    arguments: dict[str, Any]
    credential_ref: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActionEnvelope":
        if int(payload.get("delegate_version") or 1) != 2:
            raise CapabilityError("delegate_version_not_v2")
        action = payload.get("action")
        if not isinstance(action, dict):
            raise CapabilityError("action_missing")
        if set(action) - {"service_ref", "capability", "arguments", "credential_ref"}:
            raise CapabilityError("action_fields_not_allowed")
        service_ref = str(action.get("service_ref") or "").strip()
        capability = str(action.get("capability") or "").strip()
        arguments = action.get("arguments") or {}
        credential_ref = str(action.get("credential_ref") or "").strip()
        if not service_ref or not capability or not isinstance(arguments, dict):
            raise CapabilityError("action_invalid")
        return cls(service_ref, capability, arguments, credential_ref)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], CapabilityHandler] = {}

    def register(self, service_ref: str, name: str, handler: CapabilityHandler) -> None:
        clean_service_ref = str(service_ref or "").strip()
        clean_name = str(name or "").strip()
        key = (clean_service_ref, clean_name)
        if not clean_service_ref or not clean_name or key in self._handlers:
            raise CapabilityError("capability_registration_invalid")
        self._handlers[key] = handler

    def supports(self, service_ref: str, name: str) -> bool:
        return (service_ref, name) in self._handlers

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(f"{service_ref}:{name}" for service_ref, name in self._handlers))

    async def execute(self, envelope: ActionEnvelope) -> dict[str, Any]:
        handler = self._handlers.get((envelope.service_ref, envelope.capability))
        if handler is None:
            raise CapabilityError("service_capability_not_allowed")
        return await handler(envelope.arguments, envelope.credential_ref)
