from __future__ import annotations

MODE_LABELS = {
    "standby": "待命",
    "observing": "观察",
    "tasking": "任务",
    "checking": "检查",
    "risk_review": "风险复核",
    "waiting_confirm": "等待确认",
    "reporting": "汇报",
    "handoff_to_bridge": "桥接交接",
    "silent": "免打扰",
}

RISK_LABELS = {
    "normal": "正常",
    "medium": "中等",
    "high": "高",
}


def mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)


def risk_label(risk_level: str) -> str:
    return RISK_LABELS.get(risk_level, risk_level)
