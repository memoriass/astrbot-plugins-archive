"""Compatibility wrapper for the split workflow package."""

from ..workflows import (
    NATURAL_LANGUAGE_INTENT_RE,
    format_workflow_list,
    run_ani_rss_workflow,
    workflow_from_cli,
    workflow_from_natural_language,
    workflow_from_pending_shortcut,
    workflow_from_tool,
)

__all__ = [
    "NATURAL_LANGUAGE_INTENT_RE",
    "format_workflow_list",
    "run_ani_rss_workflow",
    "workflow_from_cli",
    "workflow_from_natural_language",
    "workflow_from_pending_shortcut",
    "workflow_from_tool",
]
