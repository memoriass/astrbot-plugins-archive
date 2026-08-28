from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .capability_probe import build_service_capability_evidence
from .integration_catalog import ADAPTER_CATALOG, adapter_metadata, capability_metadata
from .resource_payload import _health_url, _probe_json


async def build_integration_web_payload(runtime: Any) -> dict[str, Any]:
    gateway_url = str(runtime.config.get("assistant_service_gateway_url") or "").strip()
    gateway_health = await _probe_json(_health_url(gateway_url))
    service_capabilities = _gateway_capability_records(gateway_health)
    evidence = await build_service_capability_evidence(runtime, service_capabilities)
    webhook = getattr(runtime, "webhook_governance", None)
    companion = _webhook_companion_payload(webhook) if webhook is not None else None
    return build_integration_payload(
        gateway_url=gateway_url,
        gateway_health=gateway_health,
        capabilities=service_capabilities,
        evidence=evidence,
        companions=[companion] if companion else [],
    )


def _gateway_capability_records(gateway_health: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for service_ref, capability in sorted(_advertised_capabilities(gateway_health)):
        if service_ref not in ADAPTER_CATALOG:
            continue
        metadata = capability_metadata(capability)
        records.append(
            {
                "service_ref": service_ref,
                "capability": capability,
                "read_only": str(metadata.get("category") or "other") != "control",
            }
        )
    return records


def build_integration_payload(
    *,
    gateway_url: str,
    gateway_health: dict[str, Any],
    capabilities: list[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    companions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    advertised = _advertised_capabilities(gateway_health)
    gateway_resources = {
        str(item.get("service_ref") or ""): item
        for item in gateway_health.get("resources") or []
        if isinstance(item, dict) and str(item.get("service_ref") or "") in ADAPTER_CATALOG
    }
    child_resources: dict[str, list[dict[str, Any]]] = {}
    for item in gateway_health.get("resources") or []:
        if not isinstance(item, dict):
            continue
        parent = str(item.get("parent_service_ref") or "")
        if parent:
            child_resources.setdefault(parent, []).append(dict(item))
    adapters: list[dict[str, Any]] = []
    service_refs = {str(item.get("service_ref") or "") for item in capabilities}
    service_refs.update(gateway_resources)
    for service_ref in sorted(service_refs):
        records = [item for item in capabilities if item.get("service_ref") == service_ref]
        capability_rows = [
            _capability_row(record, evidence.get(str(record.get("capability") or ""), {}), advertised)
            for record in records
        ]
        copy = adapter_metadata(service_ref)
        resource = gateway_resources.get(service_ref, {})
        management = str(resource.get("management") or copy.get("management") or "controlled")
        category_counts = _category_counts(capability_rows)
        adapters.append(
            {
                "service_ref": service_ref,
                "name": copy.get("name") or service_ref,
                "copy_key": copy.get("copy_key") or "gateway.adapter.generic",
                "target": copy.get("target") or "受控服务",
                "authentication": copy.get("authentication") or "Gateway 托管",
                "authentication_key": copy.get("authentication_key") or "gateway.auth.managed",
                "trust_boundary": copy.get("trust_boundary") or "独立服务边界",
                "trust_boundary_key": copy.get("trust_boundary_key") or "gateway.trust.isolated",
                "deployment": copy.get("deployment") or "",
                "protocol": copy.get("protocol") or "fixed adapter contract",
                "credential_managed": bool(copy.get("credential_ref")),
                "health_capability": copy.get("health_capability") or "",
                "status": "protected" if management == "protected" else _adapter_status(capability_rows),
                "credential_status": (
                    "not_applicable"
                    if management == "protected"
                    else "not_required"
                    if management == "read_only_external" and not copy.get("credential_ref")
                    else _credential_status(capability_rows)
                ),
                "owner": str(resource.get("owner") or copy.get("owner") or "core"),
                "management": management,
                "endpoint_role": str(resource.get("endpoint_role") or ""),
                "child_resources": sorted(
                    child_resources.get(service_ref, []),
                    key=lambda item: str(item.get("service_ref") or ""),
                ),
                "capability_count": len(capability_rows),
                "available_count": sum(item["availability"] == "available" for item in capability_rows),
                "read_only_count": sum(bool(item.get("read_only")) for item in capability_rows),
                "artifact_count": sum(bool(item.get("artifact")) for item in capability_rows),
                "category_counts": category_counts,
                "capabilities": capability_rows,
            }
        )
    gateway_active = bool(gateway_health.get("ok"))
    return {
        "gateway": {
            "service_ref": "adapter.gateway",
            "name": "Adapter Gateway",
            "host": str(urlsplit(gateway_url).hostname or "202"),
            "status": "active" if gateway_active else "issue",
            "configured": bool(gateway_url),
            "executes_tasks": bool(gateway_health.get("executes_tasks", False)),
            "adapter_count": len(adapters),
            "capability_count": sum(item["capability_count"] for item in adapters),
            "available_count": sum(item["available_count"] for item in adapters),
        },
        "summary": {
            "adapters": len(adapters),
            "capabilities": sum(item["capability_count"] for item in adapters),
            "available": sum(item["available_count"] for item in adapters),
            "read_only": sum(item["read_only_count"] for item in adapters),
            "artifacts": sum(item["artifact_count"] for item in adapters),
            "restricted": sum(
                capability["availability"] == "restricted"
                for adapter in adapters
                for capability in adapter["capabilities"]
            ),
            "issues": sum(
                capability["availability"] == "issue"
                for adapter in adapters
                for capability in adapter["capabilities"]
            ),
        },
        "adapters": adapters,
        "companions": list(companions or []),
        "technical": {
            "gateway_health": gateway_health,
            "advertised_capabilities": sorted(f"{service}:{capability}" for service, capability in advertised),
        },
    }


def _webhook_companion_payload(service: Any) -> dict[str, Any]:
    status = service.status()
    sources = service.sources().get("sources", [])
    return {
        "service_ref": "plana.webhook.companion",
        "name": "Webhook 推送附属插件",
        "status": "active" if status.get("ok") else "issue",
        "deployment": "201 · AstrBot 同进程",
        "contract_version": str(status.get("companion", {}).get("contract_version") or "plana.webhook.event.v1"),
        "description": "保留原推送、模板和平台发送能力，由 Plana Core 提供策略、审计与确认边界。",
        "source_count": len(sources),
        "event_count": int(status.get("events", 0) or 0),
        "delivered": int(status.get("delivered", 0) or 0),
        "failed": int(status.get("failed", 0) or 0),
        "sources": sources,
    }


def _capability_row(
    record: dict[str, Any],
    evidence: dict[str, Any],
    advertised: set[tuple[str, str]],
) -> dict[str, Any]:
    service_ref = str(record.get("service_ref") or "")
    capability = str(record.get("capability") or "")
    registered_on_gateway = (service_ref, capability) in advertised
    availability = str(evidence.get("availability") or "unverified")
    error = str(evidence.get("error") or "")
    if advertised and not registered_on_gateway:
        availability = "issue"
        error = "gateway_registration_drift"
    metadata = capability_metadata(capability)
    return {
        "capability": capability,
        "copy_key": metadata.get("copy_key") or "gateway.capability.generic",
        "category": metadata.get("category") or "other",
        "result_type": metadata.get("result_type") or "normalized_json",
        "arguments": metadata.get("arguments") or [],
        "require_one_of": metadata.get("require_one_of") or [],
        "artifact": bool(metadata.get("artifact")),
        "availability": availability,
        "read_only": bool(record.get("read_only", True)),
        "confirmation": "not_required" if bool(record.get("read_only", True)) else "core_required",
        "lanes": list(record.get("lanes") or []),
        "default_arguments": record.get("default_arguments") if isinstance(record.get("default_arguments"), dict) else {},
        "registered_on_gateway": registered_on_gateway,
        "probe_capability": str(evidence.get("probe_capability") or ""),
        "derived": bool(evidence.get("derived")),
        "checked_at": evidence.get("checked_at"),
        "error": error,
        "limitations": evidence.get("limitations") if isinstance(evidence.get("limitations"), list) else [],
    }


def _category_counts(capabilities: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in capabilities:
        category = str(item.get("category") or "other")
        result[category] = result.get(category, 0) + 1
    return result


def _advertised_capabilities(gateway_health: dict[str, Any]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for item in gateway_health.get("capabilities") or []:
        service_ref, separator, capability = str(item or "").partition(":")
        if separator and service_ref and capability:
            result.add((service_ref, capability))
    return result


def _adapter_status(capabilities: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("availability") or "unverified") for item in capabilities}
    if "issue" in statuses:
        return "issue"
    if "restricted" in statuses:
        return "restricted"
    if statuses == {"available"}:
        return "available"
    return "unverified"


def _credential_status(capabilities: list[dict[str, Any]]) -> str:
    errors = {str(item.get("error") or "") for item in capabilities}
    if "credential_not_found" in errors or "komga_credential_missing" in errors:
        return "missing"
    if any(errors):
        return "issue"
    if capabilities and all(item.get("availability") == "available" for item in capabilities):
        return "configured"
    return "unknown"
