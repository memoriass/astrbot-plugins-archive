from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .models import COMPILED_WORKFLOWS
from .utils import _first_text, _format_score, _season_label

def format_workflow_list() -> str:
    lines = ["可用 ANI-RSS workflow："]
    for item in COMPILED_WORKFLOWS.values():
        if item.user_visible:
            lines.append(f"- {item.workflow}: {item.title} - {item.purpose}")
    lines.append("每个 workflow 只覆盖一个能力方向；底层 ANI-RSS API 调用作为流程内部步骤。")
    return "\n".join(lines)

def format_added(ani: dict[str, Any]) -> str:
    title = ani.get("title") or ani.get("mikanTitle") or "(untitled)"
    season = ani.get("season")
    subgroup = ani.get("subgroup") or ""
    enabled = "已启用" if ani.get("enable") else "未启用"
    ani_id = ani.get("id") or ""
    url = ani.get("url") or ""
    bgm_url = ani.get("bgmUrl") or ""
    score = ani.get("score")
    episode = _episode_summary(ani)
    message = str(ani.get("_message") or "添加订阅成功")

    lines = [f"ANI-RSS 添加订阅成功: {message}", f"标题: {title}", f"状态: {enabled}"]
    if season not in (None, ""):
        lines.append(f"季度: 第 {season} 季")
    if episode:
        lines.append(f"集数: {episode}")
    if subgroup:
        lines.append(f"字幕组: {subgroup}")
    if score not in (None, "", 0, 0.0):
        lines.append(f"评分: {_format_score(score)}")
    if ani_id:
        lines.append(f"订阅ID: {ani_id}")
    if bgm_url:
        lines.append(f"BGM: {bgm_url}")
    if url:
        lines.append(f"rss: {url}")
    lines.append("后续下载、过滤和刷新由 ANI-RSS 处理。")
    return "\n".join(line for line in lines if line)

def format_ani_summary(ani: dict[str, Any]) -> str:
    title = ani.get("title") or ani.get("mikanTitle") or "(untitled)"
    season = ani.get("season")
    subgroup = ani.get("subgroup") or ""
    enabled = "enabled" if ani.get("enable") else "disabled"
    ani_id = ani.get("id") or ""
    url = ani.get("url") or ""
    score = ani.get("score")
    bgm_url = ani.get("bgmUrl") or ""
    tmdb = ani.get("tmdb") if isinstance(ani.get("tmdb"), dict) else {}
    tmdb_id = tmdb.get("id") or ""
    tmdb_vote = tmdb.get("voteAverage") or ""
    episode = _episode_summary(ani)
    parts = [f"{title}"]
    if season not in (None, ""):
        parts.append(f"S{season}")
    if episode:
        parts.append(episode)
    if subgroup:
        parts.append(f"[{subgroup}]")
    if score not in (None, "", 0, 0.0):
        parts.append(f"score={_format_score(score)}")
    if tmdb_id:
        tmdb_text = f"tmdb={tmdb_id}"
        if tmdb_vote:
            tmdb_text += f"/{tmdb_vote}"
        parts.append(tmdb_text)
    parts.append(f"({enabled})")
    if ani_id:
        parts.append(f"id={ani_id}")
    if bgm_url:
        parts.append(f"bgm={bgm_url}")
    if url:
        parts.append(f"url={url}")
    return " ".join(str(part) for part in parts)

def format_preview(
    ani: dict[str, Any],
    preview: dict[str, Any],
    limit: int,
) -> str:
    items = preview.get("items") or []
    download_path = preview.get("downloadPath") or ""
    omit_list = preview.get("omitList") or []

    lines = [
        "ANI-RSS 订阅确认卡片:",
        format_ani_summary(ani),
    ]
    if download_path:
        lines.append(f"下载路径: {download_path}")
    lines.append(f"可下载条目: {len(items)}；忽略: {len(omit_list) if isinstance(omit_list, list) else omit_list}")

    for index, item in enumerate(items[: max(limit, 1)], start=1):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or "(item)"
        episode = item.get("episode")
        size = item.get("formatSize") or item.get("sizeStr") or item.get("size") or ""
        local = " local" if item.get("local") else ""
        suffix = f" E{episode}" if episode not in (None, "") else ""
        size_text = f" {size}" if size else ""
        lines.append(f"{index}. {title}{suffix}{size_text}{local}")
    if not items:
        lines.append("当前预览没有可下载条目；仍可确认创建订阅，等待后续 RSS 更新。")
    return "\n".join(lines)

def format_list(anis: list[dict[str, Any]], limit: int) -> str:
    total = len(anis)
    if total == 0:
        return "当前没有已启用的 ANI-RSS 订阅。"
    shown = anis[:limit]
    lines = [f"ANI-RSS 已启用订阅: {len(shown)}/{total}"]
    current_week = ""
    for index, ani in enumerate(shown, start=1):
        week = _subscription_week_label(ani)
        if week != current_week:
            lines.append(week)
            current_week = week
        lines.extend(_format_subscription_list_item(index, ani))
    if total > limit:
        lines.append(f"... {total - limit} more")
    return "\n".join(lines)

def format_mikan_candidates(
    candidates: list[dict[str, Any]],
    limit: int = 10,
    *,
    heading: str = "Mikan 搜索结果",
) -> str:
    if not candidates:
        return "未搜索到 Mikan 番剧。"
    lines = [f"{heading}: {len(candidates)}", "| # | 分数 | 状态 | 周期 | 标题 |", "|---|---:|---|---|---|"]
    for index, item in enumerate(candidates[:limit], start=1):
        title = item.get("title") or "(untitled)"
        exists = "已订阅" if item.get("exists") else "可订阅"
        week = item.get("_week_label") or "-"
        score = _format_score(item.get("score"))
        url = item.get("url") or ""
        cover = item.get("cover") or ""
        meta = _candidate_card_meta(item)
        summary = _candidate_summary(item)
        lines.append(f"| {index} | {score} | {exists} | {week} | {title} |")
        if cover:
            lines.append(f"  cover: {cover}")
        if meta:
            lines.append(f"  meta: {meta}")
        if summary:
            lines.append(f"  summary: {summary}")
        if url:
            lines.append(f"  {url}")
    if len(candidates) > limit:
        lines.append(f"... {len(candidates) - limit} more")
    return "\n".join(lines)

def format_mikan_recommendations(
    candidates: list[dict[str, Any]],
    *,
    total: int,
    query: str,
    season: dict[str, Any],
) -> str:
    scope = query or _season_label(season) or "当前季度"
    lines = [
        f"Mikan 推荐候选: {len(candidates)}/{total}（{scope}）",
        "| # | 分数 | 状态 | 周期 | 标题 |",
        "|---|---:|---|---|---|",
    ]
    for index, item in enumerate(candidates, start=1):
        title = item.get("title") or "(untitled)"
        exists = "已订阅" if item.get("exists") else "可订阅"
        week = item.get("_week_label") or "-"
        score = _format_score(item.get("score"))
        cover = item.get("cover") or ""
        url = item.get("url") or ""
        lines.append(f"| {index} | {score} | {exists} | {week} | {title} |")
        if cover:
            lines.append(f"  cover: {cover}")
        if url:
            lines.append(f"  {url}")
    lines.append("评分来自 ANI-RSS 的 Mikan/Bangumi 评分缓存；选定番剧后会继续拉取字幕组供选择。")
    return "\n".join(lines)

def format_mikan_groups(groups: list[dict[str, Any]], limit: int = 10) -> str:
    if not groups:
        return "未找到 Mikan 字幕组。"
    lines = [f"Mikan 字幕组 RSS: {len(groups)}"]
    for index, group in enumerate(groups[:limit], start=1):
        label = group.get("label") or "(unknown)"
        update_day = group.get("updateDay") or ""
        rss = group.get("rss") or ""
        items = group.get("items") or []
        first = ""
        if items and isinstance(items[0], dict):
            first = str(items[0].get("title") or item_name(items[0]) or "")[:80]
        tags = ", ".join(str(v) for v in group.get("tags") or [])
        suffix = f" tags={tags}" if tags else ""
        preference = " 偏好" if group.get("_preference_score") else ""
        item_count = len(items) if isinstance(items, list) else 0
        lines.append(f"{index}. {label} {update_day} items={item_count}{suffix}{preference}")
        if first:
            lines.append(f"   sample: {first}")
        if rss:
            lines.append(f"   rss: {rss}")
    if len(groups) > limit:
        lines.append(f"... {len(groups) - limit} more")
    return "\n".join(lines)

def _candidate_card_meta(item: dict[str, Any]) -> str:
    parts: list[str] = []
    air_date = _first_text(item, "air_date", "date")
    episodes = _first_text(item, "episodes", "total_episodes", "eps")
    rank = _first_text(item, "rank")
    if air_date:
        parts.append(f"开播 {air_date}")
    if episodes:
        parts.append(f"{episodes} 话")
    if rank:
        parts.append(f"Rank #{rank}")
    return " / ".join(parts)

def _candidate_summary(item: dict[str, Any]) -> str:
    summary = _first_text(item, "summary", "简介", "description", "desc")
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary[:140].rstrip() + ("..." if len(summary) > 140 else "")

def item_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("title") or "")

def _subscription_week_label(ani: dict[str, Any]) -> str:
    week = _first_text(ani, "weekLabel", "week_label", "weekday", "week")
    if week:
        return week
    return "未分组"

def _format_subscription_list_item(index: int, ani: dict[str, Any]) -> list[str]:
    title = ani.get("title") or ani.get("mikanTitle") or "(untitled)"
    season = ani.get("season")
    subgroup = ani.get("subgroup") or ""
    media_type = ani.get("type") or ""
    ani_id = ani.get("id") or ""
    score = ani.get("score")
    url = ani.get("url") or ""
    cover = _first_text(ani, "image", "coverUrl", "posterUrl", "poster", "cover")
    updated = _format_subscription_time(
        _first_text(
            ani,
            "lastDownloadTime",
            "updateTime",
            "updatedAt",
            "lastUpdateTime",
            "lastPubDate",
            "lastRefreshTime",
        ),
    )
    tags = []
    if season not in (None, ""):
        tags.append(f"第 {season} 季")
    if subgroup:
        tags.append(str(subgroup))
    if media_type:
        tags.append(str(media_type))

    lines = [f"{index}. {title}"]
    episode = _episode_summary(ani)
    if episode:
        lines.append(f"   集数: {episode}")
    if tags:
        lines.append(f"   标签: {' / '.join(tags)}")
    if score not in (None, "", 0, 0.0):
        lines.append(f"   评分: {_format_score(score)}")
    if updated:
        lines.append(f"   更新: {updated}")
    if ani_id:
        lines.append(f"   ID: {ani_id}")
    if url:
        lines.append(f"   rss: {url}")
    if cover:
        lines.append(f"   cover: {cover}")
    return lines

def _episode_summary(ani: dict[str, Any]) -> str:
    current = ani.get("currentEpisodeNumber")
    total = ani.get("totalEpisodeNumber")
    if current in (None, "") and total in (None, ""):
        return ""
    return f"{current or 0}/{total or '*'}"

def _format_subscription_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        timestamp = float(raw)
    except ValueError:
        return raw
    if timestamp > 1_000_000_000_000:
        timestamp /= 1000
    if timestamp < 946684800:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
