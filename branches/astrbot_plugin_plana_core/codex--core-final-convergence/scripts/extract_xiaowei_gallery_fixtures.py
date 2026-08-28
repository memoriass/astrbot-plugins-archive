from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


XIAOWEI_ACCOUNT = "3950564652"
MEDIA_KINDS = ("context_reaction", "command_result", "task_artifact", "risk_or_serious")
RISK = re.compile(r"(?:自杀|死亡|去世|伤害|威胁|报警|事故|隐私|密码|token|密钥|封号|申诉)", re.I)
TASK = re.compile(r"(?:代码|api|接口|数据库|日志|报错|部署|重启|下载|安装|ocr|识别|报告|总结|生成|编辑|绘制|文件|二维码|新闻|价格)", re.I)
REACTION = re.compile(r"(?:哈哈|笑死|好耶|太棒|厉害|绝了|离谱|无语|震惊|真的假的|啊这|谢谢|抱歉|早安|晚安|😂|😱|👏|🤔)", re.I)
SECRET = re.compile(r"(?i)(?:sk-[a-z0-9_-]{8,}|token\s*[:=]\s*\S+|password\s*[:=]\s*\S+)")
URL = re.compile(r"https?://\S+", re.I)
LONG_ID = re.compile(r"\b\d{6,}\b")


def extract(input_dir: Path, sources: list[str], per_class: int = 40) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    paths = [input_dir / name for name in sources] if sources else sorted(input_dir.glob("*.json"))
    for path in paths:
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        messages = sorted((row for row in messages if isinstance(row, dict)), key=_timestamp)
        if not any(_sender(row) == XIAOWEI_ACCOUNT for row in messages):
            continue
        previous_user: dict[str, Any] | None = None
        previous_xiaowei_text: dict[str, Any] | None = None
        for row in messages:
            sender = _sender(row)
            text = _plain_text(row)
            media = _media_items(row)
            if sender != XIAOWEI_ACCOUNT:
                if text:
                    previous_user = row
                continue
            if media:
                window = _window(path.name, row, previous_user, previous_xiaowei_text, media)
                if window:
                    candidates.append(window)
            if text and not media:
                previous_xiaowei_text = row
    reaction = _balanced_take(
        [row for row in candidates if row["media_kind"] == "context_reaction"], per_class
    )
    blocked = _balanced_take(
        [row for row in candidates if row["media_kind"] != "context_reaction"], per_class
    )
    selected = [*reaction, *blocked]
    return {
        "fixture_kind": "raw-derived-candidates",
        "review_status": "pending_human_review",
        "media_taxonomy": list(MEDIA_KINDS),
        "selection_policy": {
            "context_reaction_counts_for_recall": True,
            "other_media_kinds_must_be_blocked": True,
        },
        "source_files": [_source_hash(name) for name in sources],
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "context_reaction_count": len(reaction),
        "blocked_count": len(blocked),
        "cases": selected,
    }


def _window(
    source_name: str,
    media_row: dict[str, Any],
    user_row: dict[str, Any] | None,
    response_row: dict[str, Any] | None,
    media: list[dict[str, Any]],
) -> dict[str, Any] | None:
    media_at = _timestamp(media_row)
    user_at = _timestamp(user_row or {})
    response_at = _timestamp(response_row or {})
    if not user_row or media_at - user_at > 30_000 or media_at < user_at:
        return None
    user_text = _redact(_plain_text(user_row))
    response_text = _redact(_plain_text(response_row or {})) if response_at >= user_at else ""
    if not user_text:
        return None
    combined = f"{user_text} {response_text}"
    media_kind = _classify(combined, media)
    message_id = str(media_row.get("id") or media_row.get("seq") or media_at)
    return {
        "case_id": f"xw-raw-{_short_hash(f'{source_name}:{message_id}')}",
        "timestamp": "redacted",
        "user_text": user_text[:180],
        "response_text": response_text[:180],
        "xiaowei_had_image": True,
        "media_kind": media_kind,
        "expected_gallery": media_kind == "context_reaction",
        "expected_facets": _facets(combined) if media_kind == "context_reaction" else [],
        "origin": "raw-derived-candidate",
        "source_group": f"group:{_source_hash(source_name)}",
        "relative_delay_seconds": round((media_at - max(user_at, response_at)) / 1000, 2),
        "reply_anchor": _has_reply(media_row),
        "image_hash": _media_hash(media),
        "review_status": "pending_human_review",
    }


def _balanced_take(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["source_group"]), []).append(row)
    result: list[dict[str, Any]] = []
    while len(result) < limit and any(grouped.values()):
        for group in sorted(grouped):
            if grouped[group]:
                result.append(grouped[group].pop(0))
                if len(result) >= limit:
                    break
    return result


def _classify(text: str, media: list[dict[str, Any]]) -> str:
    media_types = {str(item.get("type") or "").casefold() for item in media}
    if RISK.search(text):
        return "risk_or_serious"
    if media_types.intersection({"file", "video", "audio"}):
        return "task_artifact"
    if TASK.search(text):
        return "command_result"
    if REACTION.search(text) or len(text) <= 48:
        return "context_reaction"
    return "command_result"


def _facets(text: str) -> list[str]:
    rules = (
        (r"哈哈|笑死|好耶|太棒|厉害|谢谢|😂|👏", "emotion:happy"),
        (r"离谱|无语|啊这", "emotion:speechless"),
        (r"震惊|真的假的|😱", "emotion:surprised"),
        (r"确实|同意|懂了", "tone:agree"),
        (r"离谱|吐槽", "tone:complain"),
        (r"🤔|疑惑|为什么", "tone:doubt"),
        (r"早安|晚安", "scene:greeting"),
        (r"抱歉|对不起", "scene:apology"),
    )
    result = [tag for pattern, tag in rules if re.search(pattern, text, re.I)]
    result.extend(["role:plana", "intensity:2" if len(result) > 2 else "intensity:1"])
    return list(dict.fromkeys(result))


def _redact(text: str) -> str:
    text = URL.sub("[URL]", text)
    text = SECRET.sub("[SECRET]", text)
    text = LONG_ID.sub("[ID]", text)
    text = re.sub(r"@\S+", "@用户", text)
    return re.sub(r"\s+", " ", text).strip()


def _plain_text(row: dict[str, Any]) -> str:
    content = row.get("content") or {}
    elements = content.get("elements") or []
    text = " ".join(
        str((item.get("data") or {}).get("text") or "").strip()
        for item in elements
        if str(item.get("type") or "").casefold() == "text"
    ).strip()
    return re.sub(r"\[(?:图片|视频|语音|文件)[^\]]*\]", "", text).strip()


def _media_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    content = row.get("content") or {}
    items = [*(content.get("elements") or []), *(content.get("resources") or [])]
    return [
        item for item in items
        if isinstance(item, dict)
        and str(item.get("type") or "").casefold() in {"image", "video", "audio", "file"}
    ]


def _media_hash(media: list[dict[str, Any]]) -> str:
    facts = []
    for item in media:
        data = item.get("data") or item
        facts.append(
            ":".join(
                [
                    str(item.get("type") or ""),
                    str(data.get("filename") or ""),
                    str(data.get("md5") or data.get("resourceId") or data.get("id") or ""),
                ]
            )
        )
    return hashlib.sha256("|".join(facts).encode("utf-8")).hexdigest() if facts else ""


def _has_reply(row: dict[str, Any]) -> bool:
    content = row.get("content") or {}
    return any(
        str(item.get("type") or "").casefold() == "reply"
        for item in content.get("elements") or []
        if isinstance(item, dict)
    )


def _sender(row: dict[str, Any]) -> str:
    return str((row.get("sender") or {}).get("uin") or "")


def _timestamp(row: dict[str, Any]) -> int:
    try:
        return int(row.get("timestamp") or 0)
    except (TypeError, ValueError):
        return 0


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _source_hash(value: str) -> str:
    return _short_hash(Path(value).stem)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(r"C:\git\plana_qq_history_bootstrap\input"))
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--per-class", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps(extract(args.input, args.source, args.per_class), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
