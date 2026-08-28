from __future__ import annotations

from astrbot.api import AstrBotConfig
from astrbot.api.star import Context, Star


class PlanaTTSPlugin(Star):
    """Retired compatibility shell with no runtime registrations."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    async def initialize(self) -> None:
        return None

    async def terminate(self) -> None:
        return None

__all__ = ["PlanaTTSPlugin"]
