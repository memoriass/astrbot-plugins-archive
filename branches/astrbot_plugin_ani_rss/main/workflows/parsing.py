"""Workflow request parsing facade."""

from __future__ import annotations

from .parsing_command import workflow_from_cli, workflow_from_pending_shortcut
from .parsing_natural import workflow_from_natural_language
from .parsing_tool import workflow_from_tool

__all__ = [
    "workflow_from_cli",
    "workflow_from_natural_language",
    "workflow_from_pending_shortcut",
    "workflow_from_tool",
]
