from __future__ import annotations

from ipaddress import ip_address


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


def is_loopback_request(request_obj) -> bool:
    remote_addr = str(getattr(request_obj, "remote_addr", "") or "").strip()
    if not remote_addr:
        client = getattr(request_obj, "scope", {}).get("client")
        if isinstance(client, (list, tuple)) and client:
            remote_addr = str(client[0] or "").strip()
    if not remote_addr:
        return False
    if not is_loopback_address(remote_addr):
        return False
    return not _forwarded_from_non_loopback(request_obj)


def _forwarded_from_non_loopback(request_obj) -> bool:
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
