from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr

from .plugin.filters import PlanaWarehousePassiveCaptureFilter, active_warehouse
from .plugin.runtime import PlanaMemoryWarehousePlugin

__all__ = ["PlanaMemoryWarehousePlugin"]


@filter.custom_filter(PlanaWarehousePassiveCaptureFilter, False, priority=80)
async def on_any_message(event: AstrMessageEvent) -> None:
    plugin = active_warehouse()
    if plugin is not None:
        await plugin.on_any_message(event)


@filter.on_llm_response(priority=80)
async def on_llm_response(
    event: AstrMessageEvent,
    response: Any | None = None,
) -> None:
    plugin = active_warehouse()
    if plugin is not None:
        await plugin.capture_llm_response(event, response)


@filter.command("plana_warehouse_status")
async def plana_warehouse_status(event: AstrMessageEvent):
    plugin = active_warehouse()
    if plugin is None:
        return
    async for result in plugin.plana_warehouse_status(event):
        yield result


@filter.command("plana_warehouse_search")
async def plana_warehouse_search(
    event: AstrMessageEvent,
    query: GreedyStr = "",
):
    plugin = active_warehouse()
    if plugin is None:
        return
    async for result in plugin.plana_warehouse_search(event, query):
        yield result


@filter.command("plana_warehouse_recent")
async def plana_warehouse_recent(
    event: AstrMessageEvent,
    limit: int = 5,
):
    plugin = active_warehouse()
    if plugin is None:
        return
    async for result in plugin.plana_warehouse_recent(event, limit):
        yield result


@filter.command("plana_warehouse_rebuild_index")
async def plana_warehouse_rebuild_index(
    event: AstrMessageEvent,
    confirm: str = "",
):
    plugin = active_warehouse()
    if plugin is None:
        return
    async for result in plugin.plana_warehouse_rebuild_index(event, confirm):
        yield result


@filter.command("plana_warehouse_prune")
async def plana_warehouse_prune(
    event: AstrMessageEvent,
    days: int = 0,
    confirm: str = "",
):
    plugin = active_warehouse()
    if plugin is None:
        return
    async for result in plugin.plana_warehouse_prune(event, days, confirm):
        yield result
