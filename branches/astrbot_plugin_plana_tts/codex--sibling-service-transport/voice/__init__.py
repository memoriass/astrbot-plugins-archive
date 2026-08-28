from typing import Any

__all__ = ["PlanaTTSPlugin"]


def __getattr__(name: str) -> Any:
    if name != "PlanaTTSPlugin":
        raise AttributeError(name)
    from .runtime import PlanaTTSPlugin

    return PlanaTTSPlugin
