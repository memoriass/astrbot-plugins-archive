from __future__ import annotations

import re
from typing import Any

from .models import ResourceRequirement

PERMISSIONS = {
    "read_status", "read_content", "receive_artifact", "operate", "manage_resource"
}
_REF_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,119}$")


def normalize_resource_requirements(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError("resource_requirements must be a bounded list")
    results: list[dict[str, Any]] = []
    slots: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("resource requirement must be an object")
        slot = _ref(raw.get("slot"), "slot")
        if slot in slots:
            raise ValueError("duplicate resource requirement slot")
        slots.add(slot)
        permission = str(raw.get("required_permission") or "").strip()
        if permission not in PERMISSIONS:
            raise ValueError("unsupported resource permission")
        requirement = ResourceRequirement(
            slot=slot,
            service_type=_ref(raw.get("service_type"), "service_type"),
            resource_type=_ref(raw.get("resource_type"), "resource_type"),
            required_permission=permission,
            allow_current_group=bool(raw.get("allow_current_group", True)),
            allow_current_user=bool(raw.get("allow_current_user", True)),
            allow_alias=bool(raw.get("allow_alias", True)),
        )
        results.append(requirement.to_dict())
    return results


def _ref(value: Any, field: str) -> str:
    clean = str(value or "").strip()
    if not _REF_RE.fullmatch(clean):
        raise ValueError(f"invalid {field}")
    return clean
