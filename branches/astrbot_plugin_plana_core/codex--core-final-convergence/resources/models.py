from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    service_ref: str
    service_type: str
    execution_target: str = "local"
    credential_ref: str = ""
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourceRecord:
    resource_id: str
    service_ref: str
    resource_type: str
    external_id: str
    display_name: str
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SubjectRecord:
    subject_id: str
    subject_type: str
    platform: str = ""
    external_id: str = ""
    display_name: str = ""
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    slot: str
    service_type: str
    resource_type: str
    required_permission: str
    allow_current_group: bool = True
    allow_current_user: bool = True
    allow_alias: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
