from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

from .utils import _normalize_season, _parse_kv_words


def clean_natural_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    cleaned = re.sub(r"\((?:添加|下载|订阅|追番)\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" \t\r\n，。！？!?,;；")


def natural_common_params(text: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(params or {})
    payload.update(_parse_kv_words(text))
    limit = _natural_limit(text)
    if limit:
        payload["limit"] = limit
    min_score = _natural_min_score(text)
    if min_score is not None:
        payload["min_score"] = min_score
    if re.search(r"包括已订阅|包含已订阅|include_existing\s*=\s*true", text, re.IGNORECASE):
        payload["include_existing"] = True
    return payload


def natural_season_params(text: str) -> dict[str, Any]:
    match = re.search(r"(?P<year>20\d{2})\s*(?P<season>[春夏秋冬])", text)
    if match:
        return {
            "year": int(match.group("year")),
            "season": match.group("season"),
        }

    season = ""
    if "春" in text:
        season = "春"
    elif "夏" in text:
        season = "夏"
    elif "秋" in text:
        season = "秋"
    elif "冬" in text:
        season = "冬"
    normalized = _normalize_season(season)
    return {"season": normalized} if normalized else {}


def extract_recommend_query(text: str) -> str:
    cleaned = re.sub(
        r"(列出|推荐|看看|看下|来点|有什么|有没有|当季|本季|当前季度|新番|番剧|动画|追番|推荐|筛选|列表|几部|一些|一下)",
        " ",
        text,
    )
    cleaned = re.sub(
        r"20\d{2}\s*[春夏秋冬]|limit\s*=\s*\d+|评分\s*[>=大于超过至少不低于=]*\s*\d+(?:\.\d+)?",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\b\d{1,2}\s*(?:部|个|条|项)?\b", " ", cleaned)
    query = clean_anime_query(cleaned)
    if query in {"部", "个", "条", "项", "以上", "以下"}:
        return ""
    return query


def extract_add_query_and_destination(text: str) -> tuple[str, str]:
    url = extract_url(text)
    if url:
        text = text.replace(url, " ")

    patterns = (
        r"^(?:帮我|给我|请|麻烦)?\s*(?:添加|下载|订阅|追番|加入)\s*(?P<query>.+?)(?:\s*(?:到|进|至|加入)\s*(?P<dest>.+))?$",
        r"^(?:帮我|给我|请|麻烦)?\s*(?:把|将)\s*(?P<query>.+?)\s*(?:添加|下载|订阅|追番|加入)(?:\s*(?:到|进|至|加入)\s*(?P<dest>.+))?$",
        r"^(?P<query>.+?)\s*(?:添加|下载|订阅|追番|加入)(?:\s*(?:到|进|至|加入)\s*(?P<dest>.+))?$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        query = clean_anime_query(match.group("query"))
        dest = str(match.groupdict().get("dest") or "").strip(" \t\r\n，。！？!?,;；")
        if query:
            return query, dest
    return "", ""


def extract_search_query(text: str) -> str:
    url = extract_url(text)
    if url:
        return url
    cleaned = re.sub(
        r"^(?:帮我|给我|请|麻烦)?\s*(?:搜索|查找|查一下|找一下|搜一下)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"(?i)mikan|蜜柑|rss", " ", cleaned)
    cleaned = re.sub(r"(?:有没有|有哪些|有哪几)\s*(?:字幕组|资源|候选)?", " ", cleaned)
    cleaned = re.split(
        r"(?:，|,|。|；|;|\s)+(?:看看|看下|有没有|有哪些|有哪几|候选|字幕组|不要|不用|先不|无需|别)",
        cleaned,
        maxsplit=1,
    )[0]
    cleaned = re.sub(
        r"(有没有|有哪些|有哪几|字幕组|候选|番剧|动画|订阅|的)\s*$",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return clean_anime_query(cleaned)


def clean_anime_query(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" 「」『』《》<>[]【】'\"，。！？!?,;；")
    cleaned = re.sub(r"^(一下|帮我|给我|请|麻烦|把|将)\s*", "", cleaned)
    cleaned = re.sub(r"\s*(这部|这个)?(番剧|动画|新番|订阅|rss|RSS)\s*$", "", cleaned)
    return cleaned.strip(" 「」『』《》<>[]【】'\"，。！？!?,;；")


def extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s<>'\"，。！？]+", text)
    return match.group(0).rstrip("，。！？!?,;；") if match else ""


def _natural_limit(text: str) -> int | None:
    patterns = (
        r"(?:limit|数量|条数)\s*=\s*(\d{1,2})",
        r"(?:前|推荐|列出|展示|显示|给我|来)\s*(\d{1,2})\s*(?:部|个|条|项)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            with suppress(ValueError):
                return max(int(match.group(1)), 1)
    return None


def _natural_min_score(text: str) -> float | None:
    match = re.search(
        r"(?:min_score|score|评分)\s*(?:>=|=|大于|超过|至少|不低于)?\s*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    with suppress(ValueError):
        return max(float(match.group(1)), 0.0)
    return None
