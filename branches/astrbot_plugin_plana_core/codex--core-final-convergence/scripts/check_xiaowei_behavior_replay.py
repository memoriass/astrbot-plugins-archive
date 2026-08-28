from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
ASTRBOT_ROOT = ROOT.parent / "AstrBot"
if ASTRBOT_ROOT.is_dir():
    sys.path.insert(0, str(ASTRBOT_ROOT))

from astrbot_plugin_plana_core.dialogue.behavior import BehaviorOrchestrator

XIAOWEI_ID = "3950564652"
PATTERNS = {
    "direct_answer": re.compile(r"(?:怎么|为什么|是什么|吗|？|\?)"),
    "search_tool": re.compile(r"(?:搜|查|找|状态|更新|订阅|下载|登录)"),
    "image_recommendation": re.compile(r"(?:吃|推荐|番剧|动漫|漫画|电影|图片|图)"),
    "correction": re.compile(r"(?:不是|错了|改成|重新|应该)"),
    "follow_up": re.compile(r"^(?:那|它|这个|刚才|然后|还有|再|所以)"),
    "artifact_resend": re.compile(r"(?:再发|没收到|图片呢|图呢|重发)"),
    "cancel": re.compile(r"(?:算了|取消|停|不要了|不用了)"),
    "failure_recovery": re.compile(r"(?:失败|错误|报错|不行|没用|超时)"),
    "proactive_opportunity": re.compile(r"(?:谁能|有没有人|帮我|怎么办|掉线|离线)"),
}


@dataclass(slots=True)
class _Identity:
    global_user_id: str


class _Runtime:
    config = {
        "assistant_group_proactive_mode": "conservative",
        "assistant_group_proactive_cooldown_seconds": 0,
        "assistant_group_proactive_daily_limit": 100,
    }

    def resolve_scope(self, value: object) -> str:
        return str(value or "group:replay")

    def identity_from_event(self, event: "_Event") -> _Identity:
        return _Identity(event.sender_id)


class _Event:
    def __init__(self, scenario_id: str, chat_id: str, sender_id: str, text: str) -> None:
        self.text = text
        self.sender_id = sender_id
        self.unified_msg_origin = f"group:{chat_id}"
        self.message_obj = type("MessageObject", (), {"message_id": scenario_id})()

    def get_message_str(self) -> str:
        return self.text

    def get_sender_id(self) -> str:
        return self.sender_id

    def get_sender_name(self) -> str:
        return "replay-user"

    def get_message_type(self) -> str:
        return "GroupMessage"


@dataclass(slots=True)
class _Wake:
    should_dispatch: bool
    reason: str = "xiaowei_replay"


def _trigger(row: dict[str, Any]) -> dict[str, str]:
    category = str(row.get("category") or "direct_answer")
    pattern = PATTERNS.get(category, PATTERNS["direct_answer"])
    messages = row.get("messages") if isinstance(row.get("messages"), list) else []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if str(message.get("sender_id") or "") == XIAOWEI_ID:
            continue
        text = str(message.get("text") or "")
        if pattern.search(text):
            return {
                "sender_id": str(message.get("sender_id") or "user"),
                "text": text,
            }
    return {"sender_id": "user", "text": ""}


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    orchestrator = BehaviorOrchestrator()
    runtime = _Runtime()
    counters = Counter()
    mismatches: list[dict[str, Any]] = []
    for row in rows:
        trigger = _trigger(row)
        expected_action = str(row.get("expected_action") or "direct_answer")
        expected_media = str(row.get("expected_media") or "text")
        expected_actor = str(row.get("expected_delivery_actor") or "")
        category = str(row.get("category") or "")
        wake = _Wake(category != "proactive_opportunity")
        decision = orchestrator.decide(
            runtime,
            _Event(
                str(row.get("scenario_id") or "scenario"),
                str(row.get("chat_id") or "replay"),
                trigger["sender_id"],
                trigger["text"],
            ),
            wake,
        )
        action_ok = decision.action == expected_action
        media_ok = decision.media_intent == expected_media
        actor_ok = decision.delivery_context.get("actor_id") == expected_actor
        counters["action"] += int(action_ok)
        counters["media"] += int(media_ok)
        counters["delivery"] += int(actor_ok)
        if not (action_ok and media_ok and actor_ok):
            mismatches.append(
                {
                    "scenario_id": row.get("scenario_id"),
                    "category": category,
                    "trigger": trigger["text"][:160],
                    "expected": {
                        "action": expected_action,
                        "media": expected_media,
                        "actor_id": expected_actor,
                    },
                    "actual": {
                        "action": decision.action,
                        "media": decision.media_intent,
                        "actor_id": decision.delivery_context.get("actor_id"),
                        "participation_reason": decision.participation_reason,
                    },
                }
            )
    total = len(rows)
    return {
        "total": total,
        "rates": {
            key: round(counters[key] / total, 4) if total else 0.0
            for key in ("action", "media", "delivery")
        },
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "fixture_warning": (
            "The source fixture was automatically labelled and does not preserve an explicit "
            "trigger index. Mismatches require human review before changing policy."
        ),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Replay redacted Xiaowei behavior windows.")
    parser.add_argument(
        "fixture",
        type=Path,
        nargs="?",
        default=(
            ROOT.parent
            / "plana_qq_history_bootstrap"
            / "output"
            / "xiaowei-replay"
            / "scenarios.json"
        ),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.fixture.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("fixture must contain a JSON array")
    result = evaluate([row for row in rows if isinstance(row, dict)])
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
