from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainReadDecision:
    capability: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    clarification: str = ""


def route_qbittorrent_read(query: str) -> DomainReadDecision:
    text = " ".join(str(query or "").casefold().split())
    if any(token in text for token in ("为什么", "什么意思", "怎么解决", "教程", "原理")):
        return DomainReadDecision(clarification="这是 qBittorrent 技术讨论，不执行实时查询。")
    if any(token in text for token in ("速度", "速率", "传输", "上下行", "状态", "跑得", "speed")):
        return DomainReadDecision("qbittorrent.transfer_status")
    if any(token in text for token in ("任务", "种子", "下载列表", "有哪些下载", "torrent")):
        return DomainReadDecision("qbittorrent.list_torrents", {"limit": 50})
    return DomainReadDecision(clarification="请说明要查看 qBittorrent 传输状态还是任务列表。")
