from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = Path(r"C:\git\plana_qq_history_bootstrap\input")
DEFAULT_PARSER = Path(r"C:\git\plana_qq_history_bootstrap\qq_parser.py")
HASH_NAMESPACE = "plana-route-replay-v1"
DEFAULT_TERMS = (
    "ani", "mikan", "订阅", "番剧", "字幕组", "ncqq", "二维码", "登录码",
    "机器人", "qb", "qbittorrent", "下载器", "komga", "漫画库",
)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|root|Users|var|tmp)/)\S+")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{5,}(?!\d)")
MEDIA_RE = re.compile(r"\[(?:图片|文件|视频|语音):[^\]]+\]")
MENTION_RE = re.compile(r"@[^\s,，:：]{1,64}")
REPLY_SENDER_RE = re.compile(r"\[回复 [^:\]\n]{1,64}:")


def _load_parser(path: Path):
    spec = importlib.util.spec_from_file_location("plana_qq_parser", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"qq_parser_unloadable={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _known_sender_names(parser_module: Any, path: Path) -> tuple[str, ...]:
    try:
        prefix = parser_module.read_until(path, '"messages"', max_chars=4_000_000)
    except (OSError, ValueError):
        return ()
    match = re.search(r'"senders"\s*:\s*(\[.*?\])\s*[,}]', prefix, re.S)
    if not match:
        return ()
    try:
        senders = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ()
    names = {
        str(sender.get(field) or "").strip()
        for sender in senders
        if isinstance(sender, dict)
        for field in ("name", "nickname", "remark", "groupCard")
        if len(str(sender.get(field) or "").strip()) >= 2
    }
    return tuple(sorted(names, key=len, reverse=True))


def _sanitize_text(text: str, *, sender_names: tuple[str, ...] = ()) -> str:
    clean = URL_RE.sub("<URL>", str(text or ""))
    clean = PATH_RE.sub("<PATH>", clean)
    clean = MEDIA_RE.sub("<MEDIA>", clean)
    clean = REPLY_SENDER_RE.sub("[回复 <USER>:", clean)
    clean = MENTION_RE.sub("<MENTION>", clean)
    for name in sender_names:
        clean = clean.replace(name, "<USER>")
    clean = LONG_NUMBER_RE.sub("<NUMBER>", clean)
    return " ".join(clean.split())[:500]


def _source_hash(text: str) -> str:
    payload = f"{HASH_NAMESPACE}\0{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _matches_terms(text: str, terms: Iterable[str]) -> list[str]:
    lowered = text.casefold()
    return sorted({term for term in terms if term.casefold() in lowered})


def _iter_candidates(parser_module: Any, paths: list[Path], terms: tuple[str, ...]):
    seen: set[str] = set()
    for path in paths:
        sender_names = _known_sender_names(parser_module, path)
        for message in parser_module.iter_parse_file(path, redact=True):
            text = _sanitize_text(message.text, sender_names=sender_names)
            normalized = text.casefold()
            if not text or normalized in seen:
                continue
            matched_terms = _matches_terms(text, terms)
            if not matched_terms:
                continue
            seen.add(normalized)
            yield {
                "case_id": f"qq-shadow-{len(seen):06d}",
                "origin": "qq_history_shadow_candidate",
                "source_hash": _source_hash(text),
                "text": text,
                "message_type": str(message.message_type or "group"),
                "matched_terms": matched_terms,
                "review_status": "pending_human_review",
            }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract privacy-safe QQ routing candidates for human review."
    )
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qq-parser", type=Path, default=DEFAULT_PARSER)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--term", action="append", dest="terms")
    args = parser.parse_args()
    paths = args.inputs or sorted(args.corpus.glob("*.json"))
    if not paths:
        raise SystemExit("qq_route_candidate_inputs_missing")
    if not args.qq_parser.is_file():
        raise SystemExit(f"qq_parser_missing={args.qq_parser}")
    terms = tuple(args.terms or DEFAULT_TERMS)
    parser_module = _load_parser(args.qq_parser)
    candidates = []
    for candidate in _iter_candidates(parser_module, paths, terms):
        candidates.append(candidate)
        if len(candidates) >= max(1, args.limit):
            break
    payload = {
        "fixture_kind": "qq_route_shadow_candidates",
        "review_status": "pending_human_review",
        "cases": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"qq_route_candidates={len(candidates)}:output={args.output}")


if __name__ == "__main__":
    main()
