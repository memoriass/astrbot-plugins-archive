"""Periodic health check and offline notification for ncqq instances."""
from __future__ import annotations

import base64
import datetime
import html
import pathlib
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.all import Image
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.star.star_tools import StarTools

from .monitoring import do_list_instances

if TYPE_CHECKING:
    from ..main import NCQQManagerPlugin

# Alert HTML template
_ALERT_TEMPLATE_PATH = pathlib.Path(__file__).parent.parent / "templates" / "alert.html"
_alert_template_cache: str | None = None
_alert_template_mtime: float = 0.0

_BODY_WIDTH = 420


def _get_alert_template() -> str:
    global _alert_template_cache, _alert_template_mtime
    try:
        mtime = _ALERT_TEMPLATE_PATH.stat().st_mtime
    except OSError:
        if _alert_template_cache:
            return _alert_template_cache
        raise
    if _alert_template_cache and mtime == _alert_template_mtime:
        return _alert_template_cache
    _alert_template_cache = _ALERT_TEMPLATE_PATH.read_text(encoding="utf-8")
    _alert_template_mtime = mtime
    return _alert_template_cache


def _build_alert_item(name: str, dot_class: str, detail: str, owner: str = "") -> str:
    safe_name = html.escape(str(name or ""))
    safe_detail = html.escape(str(detail or ""))
    safe_owner = html.escape(str(owner or ""))
    owner_html = f'<span class="owner-tag">{safe_owner}</span>' if owner else ""
    return (
        f'<div class="alert-item">'
        f'<span class="dot {dot_class}"></span>'
        f'<div class="inst-info">'
        f'<div class="inst-name">{safe_name}</div>'
        f'<div class="inst-detail">{safe_detail}</div>'
        f'</div>'
        f'{owner_html}'
        f'</div>'
    )


async def render_alert_card(
    title: str,
    icon: str,
    items_html: str,
    summary: str,
    accent_color: str = "#e74c3c",
) -> bytes | str:
    """Render an alert card to PNG bytes. Falls back to plain text summary."""
    try:
        template = _get_alert_template()
    except Exception:
        return summary

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = (
        template
        .replace("__BODY_WIDTH__", str(_BODY_WIDTH))
        .replace("__ACCENT_COLOR__", accent_color)
        .replace("__ALERT_ICON__", icon)
        .replace("__ALERT_TITLE__", title)
        .replace("__ALERT_TIME__", now_str)
        .replace("__ALERT_ITEMS__", items_html)
        .replace("__ALERT_SUMMARY__", summary)
    )

    try:
        from ..rendering.html_renderer import _screenshot_html
        return await _screenshot_html(html, _BODY_WIDTH)
    except Exception as e:
        logger.warning("Alert card render failed: %s", e)
        return summary


def _find_owners(
    plugin: "NCQQManagerPlugin",
    mapping: dict,
    manager_id: str,
    instance_name: str,
) -> list[tuple[str, str]]:
    """Return [(qq_id, nickname), ...] for owners of an instance ref."""
    owners = []
    instance_ref = plugin.format_instance_ref(manager_id, instance_name)
    for qq_id, data in mapping.items():
        instances = data.get("instances", [])
        legacy_match = (
            manager_id == plugin.default_manager_id()
            and instance_name in instances
        )
        if instance_ref in instances or legacy_match:
            owners.append((qq_id, data.get("nickname", "")))
    return owners


async def _load_health_snapshot(plugin: "NCQQManagerPlugin") -> dict[str, bool]:
    raw = await plugin.get_kv_data("health_snapshot", {})
    if not isinstance(raw, dict):
        return {}
    return {str(ref): value for ref, value in raw.items() if isinstance(value, bool)}


async def notify_instance_status_changes(
    plugin: "NCQQManagerPlugin",
    newly_offline: Sequence[str],
    newly_online: Sequence[str],
    instance_meta: Mapping[str, tuple[str, str]] | None = None,
    offline_details: Mapping[str, str] | None = None,
    offline_qr_urls: Mapping[str, str] | None = None,
) -> None:
    """Notify owners and the configured group about status edge changes."""
    if not newly_offline and not newly_online:
        return

    meta = instance_meta or {}
    offline_detail_map = offline_details or {}
    qr_url_map = offline_qr_urls or {}
    notify_group = str(plugin.config.get("notify_group", "")).strip()
    mapping = await plugin.get_user_mapping()

    if newly_offline:
        items_html_parts = []
        owner_messages: dict[str, list[str]] = {}

        for ref in newly_offline:
            manager_id, name = meta.get(ref, plugin.split_instance_ref(ref))
            owners = _find_owners(plugin, mapping, manager_id, name)
            owner_label = ", ".join(
                f"{nick or qq}" for qq, nick in owners
            ) if owners else "未绑定"
            detail = offline_detail_map.get(ref, "已掉线")
            items_html_parts.append(
                _build_alert_item(ref, "offline", detail, owner_label)
            )

            qr_url = qr_url_map.get(ref, "")
            for qq_id, _nick in owners:
                lines = owner_messages.setdefault(
                    qq_id,
                    ["⚠️ 以下绑定实例已掉线，请及时检查："],
                )
                lines.append(f"- {ref}：{detail}")
                if qr_url:
                    lines.append(f"  扫码链接：{qr_url}")

        for qq_id, lines in owner_messages.items():
            try:
                lines.append("可发送「ncqq login <实例>」查看状态或「ncqq qrcode <实例>」重新扫码。")
                mc = MessageChain()
                mc.message("\n".join(lines))
                await StarTools.send_message_by_id(
                    type="PrivateMessage", id=qq_id, message_chain=mc
                )
            except Exception as e:
                logger.warning("Failed to notify owner %s for offline alert: %s", qq_id, e)

        if notify_group:
            summary = f"共 {len(newly_offline)} 个实例变为离线"
            items_html = "\n".join(items_html_parts)
            rendered = await render_alert_card(
                title="实例掉线告警",
                icon="🔴",
                items_html=items_html,
                summary=summary,
                accent_color="#e74c3c",
            )
            try:
                mc = MessageChain()
                if isinstance(rendered, bytes):
                    mc.chain.append(Image.fromBase64(base64.b64encode(rendered).decode()))
                else:
                    mc.message(rendered)
                await StarTools.send_message_by_id(
                    type="GroupMessage", id=notify_group, message_chain=mc
                )
            except Exception as e:
                logger.warning("Failed to send offline alert to group %s: %s", notify_group, e)

    if newly_online:
        items_html_parts = []
        owner_messages: dict[str, list[str]] = {}

        for ref in newly_online:
            manager_id, name = meta.get(ref, plugin.split_instance_ref(ref))
            owners = _find_owners(plugin, mapping, manager_id, name)
            owner_label = ", ".join(
                f"{nick or qq}" for qq, nick in owners
            ) if owners else "未绑定"
            items_html_parts.append(
                _build_alert_item(ref, "recover", "已恢复上线", owner_label)
            )

            for qq_id, _nick in owners:
                lines = owner_messages.setdefault(
                    qq_id,
                    ["✅ 以下绑定实例已恢复上线："],
                )
                lines.append(f"- {ref}")

        for qq_id, lines in owner_messages.items():
            try:
                mc = MessageChain()
                mc.message("\n".join(lines))
                await StarTools.send_message_by_id(
                    type="PrivateMessage", id=qq_id, message_chain=mc
                )
            except Exception as e:
                logger.warning("Failed to notify owner %s for recover alert: %s", qq_id, e)

        if notify_group:
            summary = f"共 {len(newly_online)} 个实例恢复上线"
            items_html = "\n".join(items_html_parts)
            rendered = await render_alert_card(
                title="实例恢复通知",
                icon="🟢",
                items_html=items_html,
                summary=summary,
                accent_color="#2ecc71",
            )
            try:
                mc = MessageChain()
                if isinstance(rendered, bytes):
                    mc.chain.append(Image.fromBase64(base64.b64encode(rendered).decode()))
                else:
                    mc.message(rendered)
                await StarTools.send_message_by_id(
                    type="GroupMessage", id=notify_group, message_chain=mc
                )
            except Exception as e:
                logger.warning("Failed to send recover alert to group %s: %s", notify_group, e)


async def apply_health_snapshot(
    plugin: "NCQQManagerPlugin",
    current: dict[str, bool],
    instance_meta: Mapping[str, tuple[str, str]],
    *,
    notify_first_seen: bool = False,
) -> dict[str, list[str]]:
    """Persist a complete online snapshot and notify about edge changes."""
    prev = await _load_health_snapshot(plugin)
    newly_offline: list[str] = []
    newly_online: list[str] = []

    for ref, online in current.items():
        was_online = prev.get(ref)
        if was_online is True and not online:
            newly_offline.append(ref)
        elif was_online is False and online:
            newly_online.append(ref)
        elif was_online is None and notify_first_seen:
            if online:
                newly_online.append(ref)
            else:
                newly_offline.append(ref)

    await plugin.put_kv_data("health_snapshot", current)
    await notify_instance_status_changes(
        plugin,
        newly_offline,
        newly_online,
        instance_meta,
    )
    return {"offline": newly_offline, "online": newly_online}


async def apply_instance_status_event(
    plugin: "NCQQManagerPlugin",
    manager_id: str,
    instance_name: str,
    online: bool,
    *,
    notify_first_seen: bool = True,
    offline_detail: str = "",
    qr_url: str = "",
) -> dict[str, object]:
    """Apply one authoritative manager event to health_snapshot and notify once."""
    normalized_manager = plugin.normalize_manager_id(manager_id)
    ref = plugin.format_instance_ref(normalized_manager, instance_name)
    snapshot = await _load_health_snapshot(plugin)
    previous = snapshot.get(ref)
    snapshot[ref] = online
    await plugin.put_kv_data("health_snapshot", snapshot)

    should_notify = previous != online and (previous is not None or notify_first_seen)
    if should_notify:
        meta = {ref: (normalized_manager, instance_name)}
        if online:
            await notify_instance_status_changes(plugin, [], [ref], meta)
        else:
            detail = offline_detail or "已掉线"
            qr_urls = {ref: qr_url} if qr_url else {}
            await notify_instance_status_changes(
                plugin,
                [ref],
                [],
                meta,
                offline_details={ref: detail},
                offline_qr_urls=qr_urls,
            )

    return {
        "ref": ref,
        "previous": previous,
        "current": online,
        "notified": should_notify,
    }


async def do_health_check(plugin: "NCQQManagerPlugin") -> None:
    """Core health check logic. Called by cron job."""
    if not plugin.config.get("enable_offline_notify", True):
        return

    current: dict[str, bool] = {}
    instance_meta: dict[str, tuple[str, str]] = {}
    any_success = False
    for manager_id in plugin.manager_ids():
        try:
            result = await do_list_instances(
                plugin.client_for_manager(manager_id), [], True
            )
            if isinstance(result, str):
                logger.debug(
                    "Health check %s: no instances or error: %s", manager_id, result
                )
                continue
            any_success = True
            for c in result:
                name = c.get("name", "")
                if not name:
                    continue
                ref = plugin.format_instance_ref(manager_id, name)
                current[ref] = bool(c.get("bot_online", False))
                instance_meta[ref] = (manager_id, name)
        except Exception as e:
            logger.warning("Health check failed to list instances on %s: %s", manager_id, e)

    if not any_success:
        return

    await apply_health_snapshot(plugin, current, instance_meta)
