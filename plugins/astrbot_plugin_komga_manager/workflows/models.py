from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


READ_WORKFLOWS = (
    "list_libraries",
    "list_recent",
    "search_series",
    "series_detail",
    "list_books",
    "on_deck",
    "collections",
    "readlists",
)

WRITE_WORKFLOWS = (
    "scan_library",
    "analyze_library",
    "refresh_library_metadata",
    "refresh_series_metadata",
)

COMPILED_WORKFLOWS = {"ai_dispatch", *READ_WORKFLOWS, *WRITE_WORKFLOWS}


@dataclass(slots=True)
class WorkflowRequest:
    workflow: str
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "tool"

