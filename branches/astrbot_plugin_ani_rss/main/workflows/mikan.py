from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from typing import Any

from astrbot.api import logger

from .mikan_fetch import fetch_mikan_search
from .utils import _first_text, _normalize_season, _score_value

def mikan_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for section in data.get("weeks") or data.get("items") or []:
        if not isinstance(section, dict):
            continue
        week_label = section.get("weekLabel") or section.get("label") or ""
        for item in section.get("items") or []:
            if isinstance(item, dict) and item.get("url"):
                candidate = dict(item)
                if week_label:
                    candidate["_week_label"] = week_label
                candidates.append(candidate)
    return candidates

async def _enrich_mikan_candidate(plugin: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    mikan_id = _mikan_bangumi_id(str(candidate.get("url") or ""))
    if not mikan_id:
        return candidate
    try:
        data = await fetch_mikan_search(plugin, f"bangumiId: {mikan_id}")
        details = mikan_candidates(data)
    except Exception:
        return candidate
    if not details:
        return candidate
    merged = dict(candidate)
    detail = details[0]
    for key, value in detail.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    if candidate.get("score") not in (None, "", 0, 0.0) and not detail.get("score"):
        merged["score"] = candidate.get("score")
    return merged

async def _enrich_mikan_candidates_for_card(
    plugin: Any,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    async def enrich(candidate: dict[str, Any]) -> dict[str, Any]:
        enriched = await _enrich_mikan_candidate(plugin, candidate)
        return await _enrich_bangumi_metadata(enriched)

    results = await asyncio.gather(
        *(enrich(candidate) for candidate in candidates),
        return_exceptions=True,
    )
    enriched_candidates: list[dict[str, Any]] = []
    for original, result in zip(candidates, results, strict=False):
        enriched_candidates.append(result if isinstance(result, dict) else original)
    return enriched_candidates

async def _enrich_bangumi_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    subject_id = _bangumi_subject_id(_first_text(candidate, "bgmUrl", "bangumiUrl", "bgm_url"))
    if not subject_id:
        return candidate
    try:
        subject = await asyncio.to_thread(_fetch_bangumi_subject, subject_id)
    except Exception as exc:
        logger.debug("Failed to fetch Bangumi subject %s: %s", subject_id, exc)
        return candidate

    merged = dict(candidate)
    rating = subject.get("rating") if isinstance(subject.get("rating"), dict) else {}
    score = rating.get("score")
    if score not in (None, "", 0, 0.0) and _score_value(merged.get("score")) <= 0:
        merged["score"] = score
    rank = rating.get("rank")
    if rank not in (None, "", 0, 0.0):
        merged.setdefault("rank", rank)
    for source_key, target_key in (
        ("summary", "summary"),
        ("date", "air_date"),
        ("total_episodes", "episodes"),
        ("eps", "episodes"),
        ("name_cn", "name_cn"),
        ("name", "name"),
    ):
        value = subject.get(source_key)
        if value not in (None, "", [], {}):
            merged.setdefault(target_key, value)
    return merged

def _fetch_bangumi_subject(subject_id: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.bgm.tv/v0/subjects/{subject_id}",
        headers={
            "User-Agent": (
                "AstrBot ANI-RSS Plugin/1.0 "
                "(https://github.com/memoriass/astrbot_plugin_ani_rss)"
            ),
        },
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}

def _bangumi_subject_id(url: str) -> str:
    match = re.search(r"(?:bgm\.tv|bangumi\.tv)/subject/(\d+)", str(url or ""), re.I)
    return match.group(1) if match else ""

def _groups_from_candidate(candidate: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not candidate:
        return []
    groups = candidate.get("groups")
    if not isinstance(groups, list):
        return []
    return [group for group in groups if isinstance(group, dict)]

def _rank_mikan_candidates(
    candidates: list[dict[str, Any]],
    *,
    min_score: float,
    include_existing: bool,
) -> list[dict[str, Any]]:
    filtered = []
    for item in candidates:
        if item.get("exists") and not include_existing:
            continue
        if _score_value(item.get("score")) < min_score:
            continue
        filtered.append(item)
    filtered.sort(
        key=lambda item: (
            _score_value(item.get("score")),
            0 if item.get("exists") else 1,
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return filtered

def _mikan_season_payload(params: dict[str, Any]) -> dict[str, Any]:
    year = _first_text(params, "year")
    season = _normalize_season(_first_text(params, "season", "season_name"))
    if not year or not season:
        season_label = _first_text(params, "season_label", "seasonLabel")
        match = re.match(r"^(?P<year>\d{4})\s*(?P<season>[春夏秋冬])$", season_label)
        if match:
            year = match.group("year")
            season = match.group("season")
    if not year or not season:
        return {}
    try:
        return {"year": int(year), "season": season}
    except ValueError:
        return {}

def _mikan_bangumi_id(url: str) -> str:
    match = re.search(r"/Bangumi/(\d+)", url)
    return match.group(1) if match else ""
