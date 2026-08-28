from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
from pathlib import Path
from time import time
from typing import Any
import uuid


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    artifact_id: str
    path: str
    name: str
    mime_type: str
    sha256: str = ""
    expires_at: int = 0
    authorized_recipients: tuple[str, ...] = ()
    delivery_status: str = "retained"
    created_at: int = field(default_factory=lambda: int(time()))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["authorized_recipients"] = list(self.authorized_recipients)
        return data

    def available(self, *, now: int | None = None) -> bool:
        current = int(time()) if now is None else int(now)
        return (not self.expires_at or current < self.expires_at) and Path(self.path).is_file()


def artifact_reference(
    path: str,
    *,
    name: str = "",
    mime_type: str = "application/octet-stream",
    recipients: tuple[str, ...] = (),
    ttl_seconds: int = 86400,
) -> ArtifactReference:
    file_path = Path(path)
    digest = ""
    if file_path.is_file():
        hasher = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    return ArtifactReference(
        artifact_id=uuid.uuid4().hex,
        path=str(file_path),
        name=str(name or file_path.name)[:240],
        mime_type=str(mime_type or "application/octet-stream")[:120],
        sha256=digest,
        expires_at=int(time()) + max(60, int(ttl_seconds)),
        authorized_recipients=tuple(str(item)[:200] for item in recipients[:8]),
    )
