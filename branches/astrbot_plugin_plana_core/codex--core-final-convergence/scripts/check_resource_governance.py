from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.plugin.db import Database
from astrbot_plugin_plana_core.resources import (
    ResourceRecord,
    ResourceResolver,
    ResourceStorage,
    ServiceRecord,
    SubjectRecord,
    normalize_resource_requirements,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        db = Database(Path(directory) / "plana.sqlite3")
        storage = ResourceStorage(db)
        storage.initialize()
        storage.upsert_service(ServiceRecord("download.production", "download_manager", "bridge"))
        resource_id = storage.upsert_resource(ResourceRecord(
            "download:default", "download.production", "download_queue",
            "default", "NAS Download Queue",
        ))
        owner = storage.upsert_subject(SubjectRecord("qq:user:10001", "user", "qq", "10001", "Owner"))
        group = storage.upsert_subject(SubjectRecord("qq:group:20001", "group", "qq", "20001", "Beta"))
        storage.bind(
            subject_id=owner, resource_id=resource_id, relation_type="owner",
            permissions={"read_status", "receive_artifact"}, status="active",
        )
        storage.bind(
            subject_id=group, resource_id=resource_id, relation_type="member",
            permissions={"read_status"}, status="active",
        )
        storage.add_alias("beta-group", resource_id, scope_id="qq:group:20001", status="active", source="admin")
        resolver = ResourceResolver(storage)
        resolved = resolver.resolve(
            subject_ids=[group], permission="read_status", alias="beta-group",
            scope_id="qq:group:20001", service_type="download_manager",
            resource_type="download_queue",
        )
        require(resolved.status == "resolved", resolved.reason)
        require(resolved.resource["external_id"] == "default", "wrong_resource")
        denied = resolver.resolve(
            subject_ids=[group], permission="receive_artifact", service_type="download_manager",
        )
        require(denied.status == "not_found", "group_must_not_receive_qr")
        requirements = normalize_resource_requirements([{
            "slot": "target_queue", "service_type": "download_manager",
            "resource_type": "download_queue", "required_permission": "read_status",
        }])
        require(requirements[0]["slot"] == "target_queue", "resource_requirement_slot_invalid")
        require(requirements[0]["required_permission"] == "read_status", "resource_requirement_permission_invalid")
        exports = (ROOT / "resources" / "__init__.py").read_text(encoding="utf-8")
        for removed in ("ResourceAdapter", "ResourceExecutionService", "build_delegation_envelope"):
            require(removed not in exports, f"removed_resource_execution_export={removed}")
    print("resource_governance_check=ok")


if __name__ == "__main__":
    main()
