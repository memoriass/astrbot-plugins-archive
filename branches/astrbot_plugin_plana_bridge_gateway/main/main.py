from __future__ import annotations

from astrbot.api.star import register

from .bridge import PlanaBridgeGatewayPlugin as _PlanaBridgeGatewayPlugin


@register(
    "astrbot_plugin_plana_bridge_gateway",
    "soulter",
    "Plana internal bridge, controlled adapters, and Codex Runner relay.",
    "0.1.0-beta.1",
    "https://github.com/memoriass/astrbot_plugin_plana_bridge_gateway",
)
class PlanaBridgeGatewayPlugin(_PlanaBridgeGatewayPlugin):
    pass

__all__ = ["PlanaBridgeGatewayPlugin"]
