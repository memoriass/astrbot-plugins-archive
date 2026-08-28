from __future__ import annotations

from .branches import is_ani_dispatch_candidate
from .models import WorkflowRequest


def workflow_from_natural_language(text: str) -> WorkflowRequest | None:
    """Route common Chinese daily-use phrases through the controlled dispatcher."""
    raw = str(text or "").strip()
    if not raw or raw.startswith(("/", "\\")):
        return None
    if not is_ani_dispatch_candidate(raw):
        return None
    return WorkflowRequest(
        "ai_dispatch",
        target=raw,
        params={"text": raw},
        source="natural",
    )
