from __future__ import annotations

from ipaddress import ip_address
import secrets
from typing import Any


def is_loopback_request(request_obj: Any) -> bool:
    remote_addr = str(getattr(request_obj, "remote_addr", "") or "").strip()
    if not remote_addr:
        client = getattr(request_obj, "scope", {}).get("client")
        if isinstance(client, (list, tuple)) and client:
            remote_addr = str(client[0] or "").strip()
    return is_loopback_address(remote_addr) and not forwarded_from_non_loopback(request_obj)


def gateway_authorized(
    request_obj: Any,
    *,
    internal_lan_mode: bool,
    external_gateway_mode: bool,
    api_token: str,
) -> bool:
    if internal_lan_mode and is_loopback_request(request_obj):
        return True
    if not external_gateway_mode and not api_token:
        return False
    return token_authorized(request_obj, api_token, header_name="X-Plana-Gateway-Token")


def active_send_authorized(request_obj: Any, active_send_token: str) -> bool:
    return token_authorized(request_obj, active_send_token, header_name="X-Nacho-Token")


def token_authorized(request_obj: Any, expected_token: str, *, header_name: str) -> bool:
    if not expected_token:
        return False
    token = request_obj.headers.get(header_name, "").strip()
    if not token:
        token = request_obj.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return secrets.compare_digest(token, expected_token)


def core_headers(core_auth_header: str, core_token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if core_auth_header:
        headers["Authorization"] = core_auth_header
    if core_token:
        headers["X-Plana-Token"] = core_token
        if not core_auth_header:
            headers["Authorization"] = f"Bearer {core_token}"
    return headers


def is_loopback_address(value: str) -> bool:
    host = str(value or "").strip()
    if not host:
        return False
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    elif host.count(":") == 1 and "." in host:
        host = host.rsplit(":", 1)[0]
    if "%" in host:
        host = host.split("%", 1)[0]
    try:
        parsed = ip_address(host)
    except ValueError:
        return host.lower() == "localhost"
    if parsed.version == 6 and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return parsed.is_loopback


def forwarded_from_non_loopback(request_obj: Any) -> bool:
    for header in ("X-Forwarded-For", "X-Real-IP"):
        value = request_obj.headers.get(header, "")
        if not value:
            continue
        for item in value.split(","):
            client = item.strip().strip('"')
            if client and not is_loopback_address(client):
                return True
    forwarded = request_obj.headers.get("Forwarded", "")
    if not forwarded:
        return False
    for part in forwarded.split(","):
        for segment in part.split(";"):
            key, _, value = segment.strip().partition("=")
            if key.lower() != "for":
                continue
            client = value.strip().strip('"')
            if client and not is_loopback_address(client):
                return True
    return False
