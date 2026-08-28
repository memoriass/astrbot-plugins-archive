from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any


DELEGATE_CONTRACT_VERSION = "plana.codex.delegate.v1"
DELEGATE_TYPE = "codex_delegate"
REMOTE_EXECUTION_METADATA_VERSION = "plana.remote.execution.v1"

DEFAULT_REMOTE_ENGINE = "codex"
DEFAULT_EXECUTION_PROFILE = "codex_default"
DEFAULT_PROFILE_REVISION = 1

ENGINE_EXECUTION_PROFILES = {
    "codex": frozenset({"codex_default", "coding_fast", "coding_quality"}),
}

_METADATA_FIELDS = frozenset(
    {
        "execution_metadata_version",
        "engine",
        "execution_profile",
        "profile_revision",
    }
)
_FORBIDDEN_CONTROL_FIELDS = frozenset(
    {
        "api_key",
        "base_url",
        "endpoint",
        "provider",
        "token",
    }
)


@dataclass(frozen=True, slots=True)
class RemoteExecutionMetadata:
    engine: str = DEFAULT_REMOTE_ENGINE
    execution_profile: str = DEFAULT_EXECUTION_PROFILE
    profile_revision: int = DEFAULT_PROFILE_REVISION
    execution_metadata_version: str = REMOTE_EXECUTION_METADATA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_remote_execution_metadata(
    value: Mapping[str, Any] | RemoteExecutionMetadata | None = None,
    *,
    allowed_engines: Iterable[str] = (DEFAULT_REMOTE_ENGINE,),
) -> RemoteExecutionMetadata:
    """Return bounded metadata without accepting connection settings."""

    if value is None:
        raw: dict[str, Any] = {}
    elif isinstance(value, RemoteExecutionMetadata):
        raw = value.to_dict()
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise TypeError("remote_execution_metadata_must_be_mapping")

    supplied_fields = {str(key) for key in raw}
    forbidden = supplied_fields & _FORBIDDEN_CONTROL_FIELDS
    if forbidden:
        raise ValueError(f"remote_execution_control_field_forbidden:{sorted(forbidden)[0]}")
    unknown = supplied_fields - _METADATA_FIELDS
    if unknown:
        raise ValueError(f"remote_execution_metadata_field_unknown:{sorted(unknown)[0]}")

    allowed = {str(engine).strip() for engine in allowed_engines if str(engine).strip()}
    engine = str(raw.get("engine") or DEFAULT_REMOTE_ENGINE).strip().lower()
    if engine not in ENGINE_EXECUTION_PROFILES or engine not in allowed:
        raise ValueError(f"remote_execution_engine_not_allowed:{engine}")

    default_profile = DEFAULT_EXECUTION_PROFILE if engine == DEFAULT_REMOTE_ENGINE else f"{engine}_default"
    execution_profile = str(raw.get("execution_profile") or default_profile).strip().lower()
    if execution_profile not in ENGINE_EXECUTION_PROFILES[engine]:
        raise ValueError(f"remote_execution_profile_not_allowed:{engine}:{execution_profile}")

    metadata_version = str(
        raw.get("execution_metadata_version") or REMOTE_EXECUTION_METADATA_VERSION
    ).strip()
    if metadata_version != REMOTE_EXECUTION_METADATA_VERSION:
        raise ValueError(f"remote_execution_metadata_version_unsupported:{metadata_version}")

    revision_value = raw.get("profile_revision", DEFAULT_PROFILE_REVISION)
    try:
        profile_revision = int(revision_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("remote_execution_profile_revision_invalid") from exc
    if not 1 <= profile_revision <= 2_147_483_647:
        raise ValueError("remote_execution_profile_revision_invalid")

    return RemoteExecutionMetadata(
        engine=engine,
        execution_profile=execution_profile,
        profile_revision=profile_revision,
        execution_metadata_version=metadata_version,
    )


def serialize_remote_execution_metadata(
    value: Mapping[str, Any] | RemoteExecutionMetadata | None = None,
    *,
    allowed_engines: Iterable[str] = (DEFAULT_REMOTE_ENGINE,),
) -> dict[str, Any]:
    return normalize_remote_execution_metadata(
        value,
        allowed_engines=allowed_engines,
    ).to_dict()
