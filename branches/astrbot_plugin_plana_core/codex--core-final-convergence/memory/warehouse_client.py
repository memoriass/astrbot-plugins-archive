from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..plugin.sibling_services import find_sibling_service

CONTRACT_VERSION = "plana.memory_warehouse.v1"
DEFAULT_MEMORY_WAREHOUSE_URL = "http://127.0.0.1:6192/plana_warehouse"
WAREHOUSE_PLUGIN_NAME = "astrbot_plugin_plana_memory_warehouse"
MAX_RESPONSE_BYTES = 2_000_000


class MemoryWarehouseClient:
    """Thin optional client for the Plana Memory Warehouse companion plugin."""

    def __init__(self, config: dict[str, Any], runtime: Any | None = None) -> None:
        self.runtime = runtime
        self.enabled = bool(config.get("enable_memory_warehouse", True))
        self.base_url = str(
            config.get("memory_warehouse_url", DEFAULT_MEMORY_WAREHOUSE_URL)
            or DEFAULT_MEMORY_WAREHOUSE_URL
        ).strip()
        self.timeout_seconds = self._limit(
            config.get("memory_warehouse_timeout_seconds", 5),
            default=5,
            maximum=60,
        )
        self.service_key = str(config.get("plana_core_service_key", "") or "").strip()
        self.last_error = ""
        self.last_transport = ""

    @property
    def configured(self) -> bool:
        return bool(self.enabled and (self._local_service() is not None or self._http_supported()))

    def state_label(self) -> str:
        if not self.enabled:
            return "disabled"
        if self.configured:
            return "enabled"
        return "enabled_service_unavailable"

    def local_status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "url_configured": bool(self.base_url),
            "state": self.state_label(),
            "contract_version": CONTRACT_VERSION,
            "base_url": self._display_url(),
            "local_loopback_only": True,
            "in_process_available": self._local_service() is not None,
            "preferred_transport": (
                "in_process" if self._local_service() is not None else "loopback_http"
            ),
            "last_transport": self.last_transport,
            "timeout_seconds": self.timeout_seconds,
            "last_error": self.last_error,
        }

    def status(self) -> dict[str, Any]:
        result = self._request("GET", "/state")
        if not result.get("ok"):
            return result
        return {**result, "core_client": self.local_status()}

    def search(
        self,
        *,
        query: str = "",
        scope_id: str = "",
        scope_ids: list[str] | tuple[str, ...] | str | None = None,
        shared_scope_ids: list[str] | tuple[str, ...] | str | None = None,
        unified_msg_origin: str = "",
        actor_id: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "query": str(query or "")[:500],
            "scope_id": str(scope_id or "")[:200],
            "scope_ids": self._bounded_list(scope_ids, limit=200, maximum=20),
            "shared_scope_ids": self._bounded_list(
                shared_scope_ids,
                limit=200,
                maximum=20,
            ),
            "unified_msg_origin": str(unified_msg_origin or "")[:260],
            "actor_id": str(actor_id or "")[:200],
            "limit": self._limit(limit, default=10, maximum=50),
        }
        result = self._request("POST", "/evidence/search", payload=payload)
        if result.get("ok"):
            result.setdefault("coverage_status", "warehouse_index")
            result.setdefault("scope_policy", "external_warehouse_optional")
        return result

    def ingest(
        self,
        *,
        content: str,
        scope_id: str = "",
        unified_msg_origin: str = "",
        actor_id: str = "",
        actor_name: str = "",
        role: str = "system",
        event_type: str = "core_evidence",
        external_event_id: str = "",
        platform: str = "",
        message_type: str = "",
        session_id: str = "",
        group_id: str = "",
        created_at: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean = str(content or "").strip()
        if not clean:
            return self._fail("empty_content")
        payload = {
            "contract_version": CONTRACT_VERSION,
            "scope_id": str(scope_id or "")[:200],
            "unified_msg_origin": str(unified_msg_origin or "")[:260],
            "platform": str(platform or "")[:80],
            "message_type": str(message_type or "")[:80],
            "session_id": str(session_id or "")[:200],
            "group_id": str(group_id or "")[:200],
            "actor_id": str(actor_id or "")[:200],
            "actor_name": str(actor_name or "")[:160],
            "role": str(role or "system")[:40],
            "event_type": str(event_type or "core_evidence")[:80],
            "external_event_id": str(external_event_id or "")[:260],
            "content": clean,
            "created_at": int(created_at or 0),
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
        return self._request("POST", "/evidence/ingest", payload=payload)

    def bulk_ingest(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        safe_items = [item for item in items[:1000] if isinstance(item, dict)]
        if not safe_items:
            return self._fail("empty_items")
        return self._request(
            "POST",
            "/evidence/bulk-ingest",
            payload={"contract_version": CONTRACT_VERSION, "items": safe_items},
        )

    def get(self, evidence_id: str) -> dict[str, Any]:
        clean_id = str(evidence_id or "").strip()[:80]
        if not clean_id:
            return self._fail("missing_evidence_id")
        return self._request("GET", "/evidence/get", params={"evidence_id": clean_id})

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.last_error = ""
        if not self.enabled:
            return self._fail("memory_warehouse_disabled")
        service = self._local_service()
        if service is not None:
            try:
                parsed = service.request(method, path, payload, params)
            except Exception as exc:  # noqa: BLE001
                self.last_transport = "in_process"
                return self._fail(f"inprocess:{exc}"[:200])
            self.last_transport = "in_process"
            return self._validated(parsed)
        if not self._http_supported():
            return self._fail("memory_warehouse_service_unavailable")
        url = self._url(path, params)
        headers = {"Accept": "application/json"}
        if self.service_key:
            headers["X-Plana-Core-Key"] = self.service_key
        data: bytes | None = None
        if method.upper() != "GET":
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method.upper(),
        )
        self.last_transport = "loopback_http"
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                parsed = self._parse_response(self._read_limited(resp))
        except urllib.error.HTTPError as exc:
            try:
                parsed = self._parse_response(self._read_limited(exc))
            except ValueError as size_error:
                return self._fail(str(size_error))
            error = str(parsed.get("error") or f"http_{exc.code}")
            return self._fail(error)
        except urllib.error.URLError as exc:
            return self._fail(str(getattr(exc, "reason", exc))[:200])
        except ValueError as exc:
            return self._fail(str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._fail(str(exc)[:200])
        return self._validated(parsed)

    def _validated(self, parsed: Any) -> dict[str, Any]:
        if not isinstance(parsed, dict) or not parsed:
            return self._fail("invalid_response")
        if parsed.get("ok") is False or str(parsed.get("status") or "") == "error":
            error = str(parsed.get("error") or parsed.get("message") or "request_failed")
            return self._fail(error[:200])
        version = str(parsed.get("contract_version") or "")
        if version and version != CONTRACT_VERSION:
            return self._fail("contract_version_mismatch")
        return parsed

    def _remote_unsupported(self) -> bool:
        parsed = urllib.parse.urlsplit(self.base_url)
        host = (parsed.hostname or "").strip().lower()
        return bool(host and host not in {"127.0.0.1", "localhost", "::1"})

    def _http_supported(self) -> bool:
        if not self.base_url or not self.service_key or self._remote_unsupported():
            return False
        return "/api/plug/" not in urllib.parse.urlsplit(self.base_url).path

    def _local_service(self) -> Any | None:
        if self.runtime is None:
            return None
        return find_sibling_service(
            self.runtime,
            plugin_name=WAREHOUSE_PLUGIN_NAME,
            service_attr="core_service",
            required_methods=("request", "status"),
        )

    def _url(self, path: str, params: dict[str, Any] | None) -> str:
        base = self.base_url.rstrip("/")
        suffix = "/" + path.strip("/")
        url = base + suffix
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"
        return url

    def _parse_response(self, raw: bytes) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _read_limited(self, response: Any) -> bytes:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        return raw

    def _display_url(self) -> str:
        parsed = urllib.parse.urlsplit(self.base_url)
        if not parsed.query and not parsed.fragment:
            return self.base_url
        clean = parsed._replace(query="<redacted>", fragment="")
        return urllib.parse.urlunsplit(clean)

    def _fail(self, error: str) -> dict[str, Any]:
        self.last_error = error
        return {
            "ok": False,
            "contract_version": CONTRACT_VERSION,
            "coverage_status": "warehouse_unavailable",
            "scope_policy": "external_warehouse_optional",
            "error": error,
        }

    def _limit(self, value: Any, *, default: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, maximum))

    def _bounded_list(
        self,
        value: list[str] | tuple[str, ...] | str | None,
        *,
        limit: int,
        maximum: int,
    ) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            raw_items = value
        else:
            raw_items = str(value or "").replace(";", ",").split(",")
        seen: set[str] = set()
        result: list[str] = []
        for item in raw_items:
            clean = " ".join(str(item or "").split())[:limit]
            if not clean or clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
            if len(result) >= maximum:
                break
        return result
