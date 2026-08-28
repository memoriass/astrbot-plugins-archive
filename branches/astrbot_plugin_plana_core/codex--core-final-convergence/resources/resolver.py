from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .storage import ResourceStorage


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    status: str
    resource: dict[str, Any] | None = None
    candidates: tuple[dict[str, Any], ...] = ()
    reason: str = ""


class ResourceResolver:
    def __init__(self, storage: ResourceStorage) -> None:
        self.storage = storage

    def resolve(
        self, *, subject_ids: list[str], permission: str, alias: str = "",
        scope_id: str = "global", service_type: str = "", resource_type: str = "",
    ) -> ResolutionResult:
        allowed = self.storage.authorized_resources(
            subject_ids, permission=permission, service_type=service_type,
            resource_type=resource_type,
        )
        if alias:
            alias_ids = {item["resource_id"] for item in self.storage.resolve_alias(alias, scope_id=scope_id)}
            allowed = [item for item in allowed if item["resource_id"] in alias_ids]
        if len(allowed) == 1:
            return ResolutionResult("resolved", resource=allowed[0])
        if not allowed:
            return ResolutionResult("not_found", reason="no_authorized_resource")
        return ResolutionResult("ambiguous", candidates=tuple(allowed), reason="multiple_authorized_resources")
