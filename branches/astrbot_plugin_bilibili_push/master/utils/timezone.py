import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE_NAME = "Asia/Shanghai"


def get_display_timezone(name: str | None = DEFAULT_TIMEZONE_NAME):
    timezone_name = str(name or DEFAULT_TIMEZONE_NAME).strip() or DEFAULT_TIMEZONE_NAME
    offset_minutes = _parse_utc_offset(timezone_name)
    if offset_minutes is not None:
        return timezone(timedelta(minutes=offset_minutes), _offset_label(offset_minutes))
    if timezone_name.lower() in {"beijing", "china", "cst", "北京时间", "北京"}:
        return get_display_timezone(DEFAULT_TIMEZONE_NAME)
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == DEFAULT_TIMEZONE_NAME:
            return timezone(timedelta(hours=8), DEFAULT_TIMEZONE_NAME)
        return get_display_timezone(DEFAULT_TIMEZONE_NAME)


def normalize_display_timezone(name: str | None) -> str:
    timezone_name = str(name or DEFAULT_TIMEZONE_NAME).strip() or DEFAULT_TIMEZONE_NAME
    offset_minutes = _parse_utc_offset(timezone_name)
    if offset_minutes is not None:
        return _offset_label(offset_minutes)
    tz = get_display_timezone(timezone_name)
    return getattr(tz, "key", DEFAULT_TIMEZONE_NAME)


def format_bilibili_time(
    timestamp: int | str | None,
    fmt: str = "%Y-%m-%d %H:%M:%S",
    timezone_name: str | None = DEFAULT_TIMEZONE_NAME,
) -> str:
    try:
        value = int(timestamp or 0)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return datetime.fromtimestamp(
        value,
        tz=get_display_timezone(timezone_name),
    ).strftime(fmt)


def _parse_utc_offset(value: str) -> int | None:
    text = value.strip().upper().replace("GMT", "UTC")
    if text in {"UTC", "Z"}:
        return 0
    match = re.fullmatch(r"(?:UTC)?([+-])(\d{1,2})(?::?(\d{2}))?", text)
    if not match:
        return None
    sign = 1 if match.group(1) == "+" else -1
    hours = int(match.group(2))
    minutes = int(match.group(3) or 0)
    if hours > 14 or minutes > 59:
        return None
    return sign * (hours * 60 + minutes)


def _offset_label(offset_minutes: int) -> str:
    sign = "+" if offset_minutes >= 0 else "-"
    absolute = abs(offset_minutes)
    hours, minutes = divmod(absolute, 60)
    if minutes:
        return f"UTC{sign}{hours:02d}:{minutes:02d}"
    return f"UTC{sign}{hours}"
