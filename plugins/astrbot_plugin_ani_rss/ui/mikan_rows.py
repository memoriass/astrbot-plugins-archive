from __future__ import annotations

import html
from typing import Any

from .media import cover_data_uri
from .blocks import _split_table_row


def parse_mikan_rows(body_lines: list[str]) -> tuple[list[dict[str, str]], str, str]:
    rows: list[dict[str, str]] = []
    notice = ""
    prompt_lines: list[str] = []
    in_table = False
    skipped_separator = False

    for raw in body_lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("| # |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            skipped_separator = True
            continue
        if in_table and skipped_separator and line.startswith("|"):
            cells = _split_table_row(line)
            if len(cells) >= 5:
                rows.append(
                    {
                        "index": cells[0],
                        "score": cells[1],
                        "status": cells[2],
                        "week": cells[3],
                        "title": cells[4],
                        "cover": "",
                        "url": "",
                    },
                )
            continue
        if rows and line.startswith("cover:"):
            rows[-1]["cover"] = line.partition(":")[2].strip()
            continue
        if rows and line.startswith("meta:"):
            rows[-1]["meta"] = line.partition(":")[2].strip()
            continue
        if rows and line.startswith("summary:"):
            rows[-1]["summary"] = line.partition(":")[2].strip()
            continue
        if rows and line.startswith(("http://", "https://")):
            rows[-1]["url"] = line
            continue
        if line.startswith("评分来自"):
            notice = line
            continue
        if line.startswith(("回复", "任务ID:", "状态:")):
            prompt_lines.append(line)
            continue
        if rows:
            prompt_lines.append(line)

    prompt = " ".join(prompt_lines)
    return rows, notice, prompt


def render_mikan_card_section(
    label: str,
    rows: list[dict[str, str]],
    *,
    cover_proxy: dict[str, Any] | None = None,
    layout: str = "search",
) -> str:
    title = "搜索结果" if label == "Search" else label
    if layout == "search":
        rows_html = "\n".join(
            _render_mikan_candidate_list_row(row, cover_proxy=cover_proxy)
            for row in rows
        )
        return (
            '<div class="section search-section">'
            f'<div class="result-list" aria-label="{html.escape(title)}">'
            f"{rows_html}"
            "</div>"
            "</div>"
        )

    cards = "\n".join(
        _render_mikan_candidate_card(row, cover_proxy=cover_proxy)
        for row in rows
    )
    return (
        '<div class="section">'
        f'<h2 class="section-title">{html.escape(title)}</h2>'
        f'<div class="grid {html.escape(layout)}">'
        f"{cards}"
        "</div>"
        "</div>"
    )


def mikan_scope_text(heading: str, subtitle: str, rows: list[dict[str, str]]) -> str:
    if "（" in subtitle and "）" in subtitle:
        return subtitle.split("（", 1)[1].split("）", 1)[0].strip() or "当前季度"
    for row in rows:
        week = row.get("week", "")
        if week and week not in {"-", "Search"}:
            return "当前筛选"
    if heading.startswith("Mikan 选择要订阅的番剧"):
        return "选择要订阅的番剧"
    if heading.startswith("Mikan 搜索结果"):
        return "搜索结果"
    return "当前季度"


def _render_mikan_candidate_list_row(
    row: dict[str, str],
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    title = row.get("title") or "(untitled)"
    score = row.get("score") or "-"
    score_html = f'<span class="search-score">评分 {html.escape(score)}</span>' if score != "-" else ""
    status = row.get("status") or "可订阅"
    status_class = "subscribed" if status == "已订阅" else "available"
    week = row.get("week") or ""
    if week == "-":
        week = "Mikan"
    meta = _short_text(row.get("meta") or "", 42)
    summary = _short_text(row.get("summary") or "", 96)
    meta_html = f'<div class="search-details">{html.escape(meta)}</div>' if meta else ""
    summary_html = f'<div class="search-summary">{html.escape(summary)}</div>' if summary else ""
    cover = _candidate_cover_html(
        row.get("cover") or "",
        row.get("title") or "",
        row.get("index") or "",
        cover_proxy=cover_proxy,
    )
    index = html.escape(str(row.get("index") or "?")[:2])
    return (
        '<div class="search-row">'
        f"{cover}"
        '<div class="search-main">'
        f'<div class="search-title">{html.escape(title)}</div>'
        f"{meta_html}"
        f"{summary_html}"
        "</div>"
        '<div class="search-meta">'
        f"{score_html}"
        "<br>"
        f'<span class="tag {status_class}">{html.escape(status)}</span>'
        "<br>"
        f'<span class="tag week">{html.escape(week)}</span>'
        "</div>"
        f'<div class="search-index">{index}</div>'
        "</div>"
    )


def _render_mikan_candidate_card(
    row: dict[str, str],
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    title = _short_text(row.get("title") or "(untitled)", 28)
    score = row.get("score") or "-"
    score_html = f'<div class="score">{html.escape(score)}</div>' if score != "-" else '<div class="score">-</div>'
    status = row.get("status") or "可订阅"
    status_class = "subscribed" if status == "已订阅" else "available"
    week = row.get("week") or ""
    if week == "-":
        week = "Mikan"
    cover = _candidate_cover_html(
        row.get("cover") or "",
        row.get("title") or "",
        row.get("index") or "",
        cover_proxy=cover_proxy,
    )
    index = html.escape(str(row.get("index") or "?")[:2])
    return (
        '<div class="anime-card">'
        f"{cover}"
        f'<div class="index">{index}</div>'
        '<div class="anime-main">'
        f'<div class="anime-title">{html.escape(title)}</div>'
        f"{score_html}"
        '<div class="tags">'
        f'<span class="tag week">{html.escape(week)}</span>'
        f'<span class="tag {status_class}">{html.escape(status)}</span>'
        '<span class="tag">Mikan</span>'
        "</div>"
        "</div>"
        "</div>"
    )


def _candidate_cover_html(
    url: str,
    title: str,
    index: str,
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    src = cover_data_uri(url, cover_proxy=cover_proxy)
    if src:
        return f'<img class="anime-cover" src="{src}" alt="{html.escape(title)}">'
    label = html.escape(str(index or "?")[:2])
    return f'<div class="poster-placeholder">{label}</div>'


def _short_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"
