from __future__ import annotations

import asyncio
from hashlib import sha256
from time import time
from typing import Any, Callable

from ..service_gateway import ServiceGatewayClient


_PROBE_CAPABILITIES = {
    "ani_rss.production": "ani_rss.get_status",
    "ncqq.production": "ncqq.get_manager_health",
    "qbittorrent.production": "qbittorrent.transfer_status",
    "qbittorrent.tianxue": "tianxue_qb.transfer_status",
    "komga.production": "komga.list_libraries",
}
_CACHE_TTL_SECONDS = 60
_CACHE: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}


async def build_service_capability_evidence(
    runtime: Any,
    capabilities: list[dict[str, Any]],
    *,
    client_factory: Callable[..., ServiceGatewayClient] = ServiceGatewayClient,
) -> dict[str, dict[str, Any]]:
    records = [
        record
        for record in capabilities
        if isinstance(record, dict)
        and str(record.get("service_ref") or "") in _PROBE_CAPABILITIES
    ]
    if not records:
        return {}

    config = getattr(runtime, "config", {})
    enabled = bool(config.get("assistant_service_gateway_enabled", True))
    base_url = str(config.get("assistant_service_gateway_url") or "").strip()
    token = str(config.get("assistant_service_gateway_token") or "")
    timeout = int(config.get("assistant_service_gateway_timeout_seconds", 20) or 20)
    if not enabled:
        return _uniform_evidence(records, "restricted", "Adapter Gateway is disabled", "gateway_disabled")
    if not base_url or not token:
        return _uniform_evidence(records, "restricted", "Adapter Gateway is not configured", "gateway_not_configured")

    cache_key = f"{base_url}|{sha256(token.encode('utf-8')).hexdigest()[:16]}"
    cached = _CACHE.get(cache_key)
    now = time()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return {key: dict(value) for key, value in cached[1].items()}

    client = client_factory(base_url=base_url, token=token, timeout_seconds=timeout)
    service_refs = sorted({str(record.get("service_ref") or "") for record in records})
    results = await asyncio.gather(
        *(_probe_service(client, service_ref) for service_ref in service_refs),
        return_exceptions=True,
    )
    service_evidence = {
        service_ref: _service_evidence(service_ref, result)
        for service_ref, result in zip(service_refs, results, strict=True)
    }
    evidence: dict[str, dict[str, Any]] = {}
    for record in records:
        capability = str(record.get("capability") or "")
        service_ref = str(record.get("service_ref") or "")
        if not capability:
            continue
        item = dict(service_evidence[service_ref])
        item["derived"] = capability != item.get("probe_capability")
        item["probe_completed"] = int(item.get("completed") or 0)
        if item["derived"]:
            item["completed"] = 0
        evidence[capability] = item
    _CACHE[cache_key] = (now, evidence)
    return {key: dict(value) for key, value in evidence.items()}


async def _probe_service(client: ServiceGatewayClient, service_ref: str) -> dict[str, Any]:
    capability = _PROBE_CAPABILITIES[service_ref]
    return await client.query(
        request_id=f"capability-health-{int(time())}",
        service_ref=service_ref,
        capability=capability,
        resource_id="default",
        arguments={},
    )


def _service_evidence(service_ref: str, result: object) -> dict[str, Any]:
    probe_capability = _PROBE_CAPABILITIES[service_ref]
    checked_at = int(time())
    if isinstance(result, Exception):
        return _failure_evidence(probe_capability, checked_at, str(result or result.__class__.__name__))
    if not isinstance(result, dict):
        return _failure_evidence(probe_capability, checked_at, "gateway_response_invalid")
    if str(result.get("status") or "").lower() == "succeeded":
        return {
            "availability": "available",
            "limitations": [],
            "source": "adapter_gateway_probe",
            "probe_capability": probe_capability,
            "checked_at": checked_at,
            "live": True,
            "recent": 1,
            "active": 0,
            "stale": 0,
            "failed": 0,
            "completed": 1,
        }
    return _failure_evidence(probe_capability, checked_at, str(result.get("error") or "gateway_probe_failed"))


def _failure_evidence(probe_capability: str, checked_at: int, error: str) -> dict[str, Any]:
    normalized = str(error or "gateway_probe_failed")[:160]
    missing_configuration = normalized in {
        "credential_not_found",
        "service_gateway_token_missing",
        "gateway_not_configured",
    }
    limitation = (
        "Read-only service credentials are not configured"
        if normalized == "credential_not_found"
        else "Adapter Gateway is not configured"
        if missing_configuration
        else "The latest Adapter Gateway probe failed"
    )
    return {
        "availability": "restricted" if missing_configuration else "issue",
        "limitations": [limitation],
        "source": "adapter_gateway_probe",
        "probe_capability": probe_capability,
        "checked_at": checked_at,
        "live": False,
        "error": normalized,
        "recent": 1,
        "active": 0,
        "stale": 0,
        "failed": 1,
        "completed": 0,
    }


def _uniform_evidence(
    records: list[dict[str, Any]],
    availability: str,
    limitation: str,
    error: str,
) -> dict[str, dict[str, Any]]:
    checked_at = int(time())
    return {
        str(record.get("capability") or ""): {
            "availability": availability,
            "limitations": [limitation],
            "source": "adapter_gateway_configuration",
            "probe_capability": _PROBE_CAPABILITIES[str(record.get("service_ref") or "")],
            "checked_at": checked_at,
            "live": False,
            "error": error,
            "recent": 0,
            "active": 0,
            "stale": 0,
            "failed": 0,
            "completed": 0,
            "probe_completed": 0,
            "derived": str(record.get("capability") or "")
            != _PROBE_CAPABILITIES[str(record.get("service_ref") or "")],
        }
        for record in records
        if str(record.get("capability") or "")
    }
