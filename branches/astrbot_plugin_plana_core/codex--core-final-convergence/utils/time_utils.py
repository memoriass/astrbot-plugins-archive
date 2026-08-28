"""Time utility helpers for Plana Core."""

from __future__ import annotations

from datetime import datetime


def is_quiet_time(quiet_hours_str: str) -> bool:
    """Check whether the current local hour falls inside the quiet-hours window.

    Accepts a string in ``"START-END"`` format where START and END are hour
    integers (0-23).  Supports cross-midnight ranges, e.g. ``"23-6"`` means
    23:00 to 06:00 next day.

    Returns ``False`` for empty / malformed input so that missing config never
    silences Plana unexpectedly.
    """
    if not quiet_hours_str or not quiet_hours_str.strip():
        return False
    try:
        parts = quiet_hours_str.strip().split("-")
        if len(parts) != 2:
            return False
        start_hour = int(parts[0])
        end_hour = int(parts[1])
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
            return False
        now = datetime.now().hour
        if start_hour <= end_hour:
            # Same-day window, e.g. "1-7" means 01:00 to 07:00
            return start_hour <= now < end_hour
        # Cross-midnight window, e.g. "23-6" means 23:00 to 06:00
        return now >= start_hour or now < end_hour
    except (ValueError, TypeError, AttributeError):
        return False
