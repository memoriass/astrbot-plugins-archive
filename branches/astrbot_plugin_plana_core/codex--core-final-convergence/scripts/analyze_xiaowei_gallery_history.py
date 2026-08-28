from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from statistics import median
from typing import Any


XIAOWEI_ACCOUNT = "3950564652"


def analyze(input_dir: Path) -> dict[str, Any]:
    files = []
    total_messages = 0
    media_messages = 0
    image_messages = 0
    same_message_text_media = 0
    text_then_image_delays: list[float] = []
    all_image_pair_delays: list[float] = []
    image_hashes: set[str] = set()
    taxonomy_counts = {
        "context_reaction": 0,
        "command_result": 0,
        "task_artifact": 0,
        "risk_or_serious": 0,
    }
    for path in sorted(input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        matched = [row for row in messages if _sender(row) == XIAOWEI_ACCOUNT]
        if not matched:
            continue
        matched.sort(key=_timestamp)
        file_images = 0
        previous_text_only: dict[str, Any] | None = None
        for row in matched:
            total_messages += 1
            timestamp = _timestamp(row)
            media_types = _media_types(row)
            has_media = bool(media_types)
            has_image = "image" in media_types
            has_text = bool(_plain_text(row))
            if has_media:
                media_messages += 1
                file_images += 1
                image_hashes.update(_media_hashes(row))
                previous_text = _plain_text(previous_text_only or {})
                media_kind = _media_kind(f"{previous_text} {_plain_text(row)}", media_types)
                taxonomy_counts[media_kind] += 1
                if has_image:
                    image_messages += 1
                if has_text:
                    same_message_text_media += 1
                if has_image and previous_text_only is not None:
                    delay = (timestamp - _timestamp(previous_text_only)) / 1000
                    if 0 <= delay <= 30:
                        all_image_pair_delays.append(delay)
                        if media_kind == "context_reaction":
                            text_then_image_delays.append(delay)
                previous_text_only = None
            if has_text and not has_media:
                previous_text_only = row
        files.append({
            "file": path.name,
            "messages": len(matched),
            "media_messages": file_images,
        })
    ordered = sorted(text_then_image_delays)
    return {
        "account": XIAOWEI_ACCOUNT,
        "files": files,
        "message_count": total_messages,
        "media_message_count": media_messages,
        "image_message_count": image_messages,
        "same_message_text_media_count": same_message_text_media,
        "text_then_image_within_30s": len(ordered),
        "all_image_text_pairs_within_30s": len(all_image_pair_delays),
        "median_delay_seconds": round(median(ordered), 2) if ordered else 0,
        "p90_delay_seconds": round(_percentile(ordered, 0.9), 2) if ordered else 0,
        "unique_redacted_image_hashes": len(image_hashes),
        "media_taxonomy_counts": taxonomy_counts,
        "metric_definition": {
            "text_then_image_within_30s": "one image-bearing message paired with the immediately preceding unconsumed Xiaowei text-only message within 30 seconds",
            "media_message_count": "messages containing image, video, audio or file media",
            "image_message_count": "messages containing at least one image",
        },
    }


def _sender(row: dict[str, Any]) -> str:
    return str((row.get("sender") or {}).get("uin") or "")


def _timestamp(row: dict[str, Any]) -> int:
    try:
        return int(row.get("timestamp") or 0)
    except (TypeError, ValueError):
        return 0


def _plain_text(row: dict[str, Any]) -> str:
    elements = (row.get("content") or {}).get("elements") or []
    text = " ".join(
        str((item.get("data") or {}).get("text") or "").strip()
        for item in elements
        if str(item.get("type") or "").lower() == "text"
    ).strip()
    return re.sub(r"\[(?:图片|视频|语音|文件)[^\]]*\]", "", text).strip()


def _has_media(row: dict[str, Any]) -> bool:
    return bool(_media_types(row))


def _media_types(row: dict[str, Any]) -> set[str]:
    content = row.get("content") or {}
    elements = content.get("elements") or []
    resources = content.get("resources") or []
    return {
        str(item.get("type") or "").lower()
        for item in [*elements, *resources]
        if str(item.get("type") or "").lower() in {"image", "video", "audio", "file"}
    }


def _media_kind(text: str, media_types: set[str]) -> str:
    if re.search(r"(?:自杀|死亡|去世|伤害|威胁|报警|隐私|密码|token|封号|申诉)", text, re.I):
        return "risk_or_serious"
    if media_types.intersection({"file", "video", "audio"}):
        return "task_artifact"
    if re.search(r"(?:代码|api|接口|数据库|日志|部署|下载|ocr|报告|生成|编辑|二维码|新闻|价格)", text, re.I):
        return "command_result"
    return "context_reaction"


def _media_hashes(row: dict[str, Any]) -> set[str]:
    content = row.get("content") or {}
    items = [*(content.get("elements") or []), *(content.get("resources") or [])]
    result = set()
    for item in items:
        if str(item.get("type") or "").lower() not in {"image", "video", "audio", "file"}:
            continue
        data = item.get("data") or item
        filename = str(data.get("filename") or "").strip().lower()
        if filename:
            result.add(hashlib.sha256(filename.encode("utf-8")).hexdigest())
    return result


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
    return values[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(r"C:\git\plana_qq_history_bootstrap\input"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.input)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
