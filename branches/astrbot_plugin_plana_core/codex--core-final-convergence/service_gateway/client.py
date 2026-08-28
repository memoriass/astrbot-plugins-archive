from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlparse

import aiohttp


class ServiceGatewayError(RuntimeError):
    pass


class ServiceGatewayClient:
    """Authenticated client for the independent deterministic adapter gateway."""

    def __init__(self, *, base_url: str, token: str, timeout_seconds: int = 20) -> None:
        self.base_url = self._validate_base_url(base_url)
        self.token = str(token or "")
        self.timeout_seconds = max(1, min(int(timeout_seconds or 20), 120))

    async def query(self, *, request_id: str, service_ref: str, capability: str,
                    resource_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            endpoint="query", request_id=request_id, service_ref=service_ref,
            capability=capability, resource_id=resource_id, arguments=arguments,
            confirmed=False,
        )

    async def execute(self, *, request_id: str, service_ref: str, capability: str,
                      resource_id: str, arguments: dict[str, Any], confirmed: bool) -> dict[str, Any]:
        if confirmed is not True:
            raise ServiceGatewayError("service_execution_confirmation_required")
        return await self._call(
            endpoint="execute", request_id=request_id, service_ref=service_ref,
            capability=capability, resource_id=resource_id, arguments=arguments,
            confirmed=True,
        )

    async def _call(self, *, endpoint: str, request_id: str, service_ref: str,
                    capability: str, resource_id: str, arguments: dict[str, Any],
                    confirmed: bool) -> dict[str, Any]:
        if not self.token:
            raise ServiceGatewayError("service_gateway_token_missing")
        payload = {
            "request_id": str(request_id or "")[:120],
            "service_ref": str(service_ref or "")[:120],
            "capability": str(capability or "")[:120],
            "resource_id": str(resource_id or "default")[:120],
            "arguments": self._scalar_arguments(arguments),
        }
        if endpoint == "execute":
            payload["confirmed"] = confirmed
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = hmac.new(self.token.encode("utf-8"), timestamp.encode("ascii") + b"\n" + body,
                             hashlib.sha256).hexdigest()
        headers = {"Content-Type": "application/json", "X-Plana-Timestamp": timestamp,
                   "X-Plana-Signature": signature}
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds, connect=min(5, self.timeout_seconds))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/v1/capabilities/{endpoint}", data=body,
                                        headers=headers) as response:
                    result = await response.json(content_type=None)
                    if response.status >= 400:
                        error = result.get("error") if isinstance(result, dict) else "gateway_request_failed"
                        raise ServiceGatewayError(str(error or f"gateway_http_{response.status}"))
        except aiohttp.ClientError as exc:
            raise ServiceGatewayError("service_gateway_unreachable") from exc
        if not isinstance(result, dict):
            raise ServiceGatewayError("service_gateway_response_invalid")
        return result

    @staticmethod
    def _scalar_arguments(arguments: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
        if not isinstance(arguments, dict) or len(arguments) > 20:
            raise ServiceGatewayError("service_arguments_invalid")
        normalized: dict[str, str | int | float | bool | None] = {}
        for raw_key, value in arguments.items():
            key = str(raw_key or "").strip()
            if not key or len(key) > 120 or value is not None and not isinstance(value, (str, int, float, bool)):
                raise ServiceGatewayError("service_arguments_invalid")
            normalized[key] = value[:1000] if isinstance(value, str) else value
        return normalized

    @staticmethod
    def _validate_base_url(value: str) -> str:
        clean = str(value or "").strip().rstrip("/")
        parsed = urlparse(clean)
        if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
            raise ServiceGatewayError("service_gateway_url_invalid")
        return clean
