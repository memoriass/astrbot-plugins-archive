from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "astrbot_plugin_plana_core"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"load_failed={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ensure_package(PKG, ROOT)
_ensure_package(f"{PKG}.proactive", ROOT / "proactive")
schedule_module = _load(
    f"{PKG}.proactive.schedule_parser",
    ROOT / "proactive" / "schedule_parser.py",
)

parse_reminder_time = schedule_module.parse_reminder_time


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute).timestamp())


def main() -> None:
    base = ts(2026, 6, 29, 8, 0)
    cases = [
        ("10分钟后提醒我", 600),
        ("半小时后提醒我", 1800),
        ("in 2 hours remind me", 7200),
    ]
    for text, delay in cases:
        parsed = parse_reminder_time(text, now=base)
        require(parsed["matched"], f"relative_not_matched={text}:{parsed}")
        require(parsed["delay_seconds"] == delay, f"relative_delay={text}:{parsed}")
    tomorrow = parse_reminder_time("明天9点提醒开会", now=base)
    require(tomorrow["scheduled_at"] == ts(2026, 6, 30, 9), f"tomorrow={tomorrow}")
    tonight = parse_reminder_time("今晚8点提醒复盘", now=base)
    require(tonight["scheduled_at"] == ts(2026, 6, 29, 20), f"tonight={tonight}")
    next_monday = parse_reminder_time("下周一上午9点提醒", now=base)
    require(next_monday["scheduled_at"] == ts(2026, 7, 6, 9), f"next_monday={next_monday}")
    next_friday = parse_reminder_time("next friday at 3pm", now=base)
    require(next_friday["scheduled_at"] == ts(2026, 7, 3, 15), f"next_friday={next_friday}")
    tomorrow_if_past = parse_reminder_time("9点提醒", now=ts(2026, 6, 29, 10))
    require(tomorrow_if_past["scheduled_at"] == ts(2026, 6, 30, 9), f"past={tomorrow_if_past}")

    print("reminder_schedule_check=ok")


if __name__ == "__main__":
    main()
