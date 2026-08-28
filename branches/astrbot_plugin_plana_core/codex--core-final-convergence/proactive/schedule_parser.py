from __future__ import annotations

import re
from datetime import datetime, timedelta
from time import time
from typing import Any

WEEKDAY_NAMES = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
    "1": 0,
    "2": 1,
    "3": 2,
    "4": 3,
    "5": 4,
    "6": 5,
    "7": 6,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

CN_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}

UNIT_SECONDS = {
    "秒": 1,
    "秒钟": 1,
    "second": 1,
    "seconds": 1,
    "分钟": 60,
    "分": 60,
    "minute": 60,
    "minutes": 60,
    "小时": 3600,
    "钟头": 3600,
    "hour": 3600,
    "hours": 3600,
    "天": 86400,
    "日": 86400,
    "day": 86400,
    "days": 86400,
    "周": 604800,
    "星期": 604800,
    "week": 604800,
    "weeks": 604800,
}


def parse_reminder_time(text: str, now: int | None = None) -> dict[str, Any]:
    """Parse common reminder time phrases into a Unix timestamp."""
    base_ts = int(now if now is not None else time())
    clean = " ".join(str(text or "").strip().split())
    if not clean:
        return _empty(base_ts)
    relative = _parse_relative(clean, base_ts)
    if relative["matched"]:
        return relative
    absolute = _parse_absolute(clean, base_ts)
    if absolute["matched"]:
        return absolute
    later = clean.lower()
    if "稍后" in later or "later" in later:
        return _matched(base_ts, base_ts + 600, "稍后")
    return _empty(base_ts)


def _parse_relative(text: str, base_ts: int) -> dict[str, Any]:
    if "半小时后" in text or "半个小时后" in text:
        return _matched(base_ts, base_ts + 1800, "半小时后")
    pattern = re.compile(
        r"(?:in\s*)?([0-9]+|[一二两三四五六七八九十]{1,2})\s*"
        r"(秒钟|秒|分钟|分|小时|钟头|天|日|周|星期|seconds?|minutes?|hours?|days?|weeks?)"
        r"(?:后|later)?",
        re.I,
    )
    match = pattern.search(text)
    if not match:
        return _empty(base_ts)
    amount = _number(match.group(1))
    unit = match.group(2).lower()
    seconds = amount * UNIT_SECONDS.get(unit, 0)
    if seconds <= 0:
        return _empty(base_ts)
    return _matched(base_ts, base_ts + seconds, match.group(0))


def _parse_absolute(text: str, base_ts: int) -> dict[str, Any]:
    base = datetime.fromtimestamp(base_ts)
    lowered = text.lower()
    day_offset = _day_offset(lowered)
    weekday = _weekday(lowered)
    time_of_day = _time_of_day(text)
    if day_offset is None and weekday is None and time_of_day is None:
        return _empty(base_ts)
    target = base
    if weekday is not None:
        days = (weekday - base.weekday()) % 7
        if days == 0:
            days += 7
        target = base + timedelta(days=days)
    elif day_offset is not None:
        target = base + timedelta(days=day_offset)
    hour, minute = time_of_day if time_of_day is not None else (9, 0)
    target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday is None and day_offset is None and target.timestamp() <= base_ts:
        target += timedelta(days=1)
    return _matched(base_ts, int(target.timestamp()), _absolute_expression(text))


def _time_of_day(text: str) -> tuple[int, int] | None:
    period = _period(text)
    colon = re.search(r"([0-2]?\d)[:：]([0-5]\d)", text)
    if colon:
        return _apply_period(int(colon.group(1)), int(colon.group(2)), period)
    point = re.search(r"([0-2]?\d|[一二两三四五六七八九十]{1,2})\s*[点時时]", text)
    if point:
        hour = _number(point.group(1))
        minute = 30 if "半" in text[point.end() : point.end() + 2] else 0
        return _apply_period(hour, minute, period)
    english = re.search(r"\bat\s*([0-2]?\d)(?::([0-5]\d))?\s*(am|pm)?\b", text, re.I)
    if english:
        hour = int(english.group(1))
        minute = int(english.group(2) or 0)
        suffix = (english.group(3) or "").lower()
        if suffix == "pm" and hour < 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
        return hour, minute
    return None


def _day_offset(text: str) -> int | None:
    if "大后天" in text:
        return 3
    if "后天" in text:
        return 2
    if "明天" in text or "明日" in text or "tomorrow" in text:
        return 1
    if "今天" in text or "今晚" in text or "today" in text or "tonight" in text:
        return 0
    return None


def _weekday(text: str) -> int | None:
    chinese = re.search(r"(?:下周|下星期|下礼拜|周|星期|礼拜)([一二三四五六日天1-7])", text)
    if chinese:
        return WEEKDAY_NAMES[chinese.group(1)]
    english = re.search(
        r"\b(?:next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b",
        text,
        re.I,
    )
    if english:
        return WEEKDAY_NAMES[english.group(1).lower()]
    return None


def _period(text: str) -> str:
    if any(token in text for token in ("下午", "晚上", "今晚", "傍晚")):
        return "pm"
    if any(token in text for token in ("凌晨", "早上", "上午", "明早")):
        return "am"
    if "中午" in text:
        return "noon"
    return ""


def _apply_period(hour: int, minute: int, period: str) -> tuple[int, int]:
    if period == "pm" and hour < 12:
        hour += 12
    if period == "am" and hour == 12:
        hour = 0
    if period == "noon" and hour < 11:
        hour += 12
    return max(0, min(hour, 23)), max(0, min(minute, 59))


def _number(raw: str) -> int:
    text = str(raw)
    if text.isdigit():
        return int(text)
    if text in CN_NUMBERS:
        return CN_NUMBERS[text]
    if text.startswith("十") and len(text) == 2:
        return 10 + CN_NUMBERS.get(text[1], 0)
    if text.endswith("十") and len(text) == 2:
        return CN_NUMBERS.get(text[0], 0) * 10
    return 0


def _absolute_expression(text: str) -> str:
    return str(text or "").strip()[:120]


def _matched(base_ts: int, scheduled_at: int, expression: str) -> dict[str, Any]:
    return {
        "matched": True,
        "now": base_ts,
        "scheduled_at": max(base_ts, int(scheduled_at)),
        "delay_seconds": max(0, int(scheduled_at) - base_ts),
        "expression": expression,
    }


def _empty(base_ts: int) -> dict[str, Any]:
    return {
        "matched": False,
        "now": base_ts,
        "scheduled_at": 0,
        "delay_seconds": 0,
        "expression": "",
    }
