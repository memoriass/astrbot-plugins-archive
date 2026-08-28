"""Receive ncqq-manager offline alert POST events."""
from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from aiohttp import web
from astrbot.api import logger

from .health_check import apply_instance_status_event

if TYPE_CHECKING:
    from aiohttp.web_request import Request

    from ..main import NCQQManagerPlugin

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 6198
_DEFAULT_PATH = "/ncqq-manager/alerts"
_OFFLINE_EVENTS = {"login_lost", "instance_offline"}
_ONLINE_EVENTS = {"instance_online", "login_recovered", "instance_recovered"}


class OfflineWebhookError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class OfflineWebhookConfig:
    enabled: bool
    host: str
    port: int
    path: str
    token: str


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}
    return default


def _as_port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_PORT
    if 1 <= port <= 65535:
        return port
    return _DEFAULT_PORT


def _normalize_path(value: object) -> str:
    text = str(value or "").strip() or _DEFAULT_PATH
    if not text.startswith("/"):
        text = f"/{text}"
    return text.rstrip("/") or _DEFAULT_PATH


def _config_from_plugin(config: Mapping[str, Any]) -> OfflineWebhookConfig:
    return OfflineWebhookConfig(
        enabled=_as_bool(config.get("enable_alert_webhook"), default=False),
        host=str(config.get("alert_webhook_host") or _DEFAULT_HOST).strip() or _DEFAULT_HOST,
        port=_as_port(config.get("alert_webhook_port")),
        path=_normalize_path(config.get("alert_webhook_path")),
        token=str(config.get("alert_webhook_token") or "").strip(),
    )


def _is_loopback_host(host: str) -> bool:
    lowered = host.strip().lower()
    if lowered in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def _canonical_url(value: object) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def _request_token(request: "Request") -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (
        request.headers.get("X-NCQQ-Webhook-Token", "")
        or request.query.get("token", "")
        or request.query.get("key", "")
    ).strip()


def _token_matches(configured: str, received: str) -> bool:
    if not configured:
        return True
    return bool(received) and hmac.compare_digest(configured, received)


def _payload_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _resolve_manager_id(
    plugin: "NCQQManagerPlugin",
    payload: Mapping[str, Any],
    params: Mapping[str, str],
) -> str:
    for key in ("manager_id", "manager", "panel", "site"):
        candidate = params.get(key) or payload.get(key)
        if candidate:
            try:
                return plugin.normalize_manager_id(candidate)
            except KeyError as exc:
                raise OfflineWebhookError(f"unknown manager_id: {candidate}") from exc

    dashboard_url = _canonical_url(payload.get("dashboard_url"))
    qr_url = _canonical_url(payload.get("qr_url"))
    for manager_id in plugin.manager_ids():
        try:
            profile_url = _canonical_url(plugin.clients.profile(manager_id).manager_url)
        except Exception:
            continue
        if profile_url and (
            profile_url == dashboard_url
            or (qr_url and qr_url.startswith(profile_url))
        ):
            return manager_id

    if len(plugin.manager_ids()) > 1:
        logger.warning(
            "ncqq alert webhook missing manager_id; falling back to default manager"
        )
    return plugin.default_manager_id()


def _offline_detail(event: str, payload: Mapping[str, Any]) -> str:
    node_id = _payload_text(payload, "node_id")
    uin = _payload_text(payload, "uin")
    reason = _payload_text(payload, "reason")
    if event == "login_lost":
        parts = ["登录状态丢失"]
    else:
        parts = ["实例离线"]
    if uin and uin != "未知":
        parts.append(f"QQ {uin}")
    if node_id:
        parts.append(f"节点 {node_id}")
    if reason:
        parts.append(reason)
    return " · ".join(parts)


async def handle_offline_webhook_payload(
    plugin: "NCQQManagerPlugin",
    payload: Mapping[str, Any],
    params: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Apply one ncqq-manager alert payload to the plugin health snapshot."""
    params = params or {}
    event = _payload_text(payload, "event").lower()
    if event not in _OFFLINE_EVENTS and event not in _ONLINE_EVENTS:
        raise OfflineWebhookError(f"unsupported event: {event or '<empty>'}")

    instance_name = _payload_text(payload, "instance", "instance_name", "name")
    if not instance_name:
        raise OfflineWebhookError("missing instance")

    manager_id = _resolve_manager_id(plugin, payload, params)
    online = event in _ONLINE_EVENTS
    result = await apply_instance_status_event(
        plugin,
        manager_id,
        instance_name,
        online,
        notify_first_seen=not online,
        offline_detail=_offline_detail(event, payload),
        qr_url=_payload_text(payload, "qr_url"),
    )
    result["event"] = event
    result["manager_id"] = manager_id
    result["instance"] = instance_name
    return result


class OfflineWebhookServer:
    """Small aiohttp listener for ncqq-manager alert webhooks."""

    def __init__(self, plugin: "NCQQManagerPlugin"):
        self._plugin = plugin
        self._config = _config_from_plugin(plugin.config)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        if not self._config.enabled:
            return
        if self._runner is not None:
            return
        if not self._config.token and not _is_loopback_host(self._config.host):
            logger.warning(
                "ncqq alert webhook not started: non-loopback bind requires alert_webhook_token"
            )
            return

        app = web.Application(client_max_size=64 * 1024)
        app.router.add_post(self._config.path, self._handle)
        self._runner = web.AppRunner(app)
        try:
            await self._runner.setup()
            self._site = web.TCPSite(
                self._runner,
                self._config.host,
                self._config.port,
            )
            await self._site.start()
            logger.info(
                "ncqq alert webhook listening on %s:%s%s",
                self._config.host,
                self._config.port,
                self._config.path,
            )
        except Exception as exc:
            logger.warning("ncqq alert webhook failed to start: %s", exc)
            await self.stop()

    async def stop(self) -> None:
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception as exc:
                logger.debug("ncqq alert webhook cleanup failed: %s", exc)
        self._site = None
        self._runner = None

    async def _handle(self, request: "Request") -> web.Response:
        if not _token_matches(self._config.token, _request_token(request)):
            return web.json_response({"status": "error", "error": "unauthorized"}, status=401)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"status": "error", "error": "invalid json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"status": "error", "error": "payload must be object"}, status=400)

        try:
            result = await handle_offline_webhook_payload(
                self._plugin,
                payload,
                request.query,
            )
        except OfflineWebhookError as exc:
            return web.json_response(
                {"status": "error", "error": str(exc)},
                status=exc.status,
            )
        except Exception as exc:
            logger.warning("ncqq alert webhook handling failed: %s", exc)
            return web.json_response({"status": "error", "error": "internal error"}, status=500)

        return web.json_response({"status": "ok", **result})
