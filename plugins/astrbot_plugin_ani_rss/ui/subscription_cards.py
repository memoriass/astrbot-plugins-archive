from __future__ import annotations

import html
import re
from typing import Any

from .blocks import extract_heading
from .media import cover_data_uri, source_icon_data_uri

SUBSCRIPTION_LIST_HEADINGS = ("ANI-RSS 已启用订阅",)


def is_subscription_list_text(text: str, *, title: str = "") -> bool:
    lines = [line.rstrip() for line in str(text or "").strip().splitlines()]
    heading, _, _ = extract_heading(lines, title=title)
    return heading.startswith(SUBSCRIPTION_LIST_HEADINGS)


def build_subscription_list_card_html(
    heading: str,
    subtitle: str,
    body_lines: list[str],
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    if not heading.startswith(SUBSCRIPTION_LIST_HEADINGS):
        return ""

    rows = parse_subscription_rows(body_lines)
    groups = _group_rows(rows)
    if not groups:
        sections_html = '<div class="empty">当前没有已启用的 ANI-RSS 订阅。</div>'
    else:
        sections_html = "\n".join(
            _render_week_section(week, week_rows, cover_proxy=cover_proxy)
            for week, week_rows in groups
        )
    source_icon = source_icon_data_uri([], heading)
    subtitle_text = subtitle or f"{len(rows)} 项正在订阅"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      padding: 0;
      background: #f5f7fa;
      color: #303133;
      font-family: "PingFang SC", "Noto Sans SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    .page {{
      padding: 10px;
      width: 100%;
    }}
    .panel {{
      background: #ffffff;
      border: 1px solid #ebeef5;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(31, 45, 61, 0.05);
      overflow: hidden;
    }}
    .header {{
      padding: 12px 14px 10px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid #ebeef5;
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 9px;
      min-width: 0;
    }}
    .source-icon {{
      flex: 0 0 42px;
      border-radius: 8px;
      background: #ecf5ff;
    }}
    .title-block {{
      min-width: 0;
    }}
    .eyebrow {{
      color: #409eff;
      font-size: 12px;
      font-weight: 750;
    }}
    h1 {{
      margin: 2px 0 0 0;
      color: #303133;
      font-size: 20px;
      line-height: 1.2;
      font-weight: 750;
    }}
    .summary {{
      flex: 0 0 auto;
      color: #909399;
      font-size: 13px;
    }}
    .body {{
      padding: 10px;
    }}
    .week-section {{
      margin-bottom: 12px;
    }}
    .week-section:last-child {{
      margin-bottom: 0;
    }}
    .week-title {{
      margin: 2px 0 7px 0;
      color: #111827;
      font-size: 18px;
      line-height: 1.2;
      font-weight: 800;
    }}
    .grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: stretch;
      justify-content: flex-start;
    }}
    .sub-card {{
      width: 404px;
      flex: 0 0 404px;
      min-height: 120px;
      display: flex;
      padding: 10px;
      border: 1px solid #ebeef5;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 3px 8px rgba(31, 45, 61, 0.035);
    }}
    .poster,
    .poster-placeholder {{
      width: 72px;
      height: 98px;
      border-radius: 7px;
      flex: 0 0 auto;
      object-fit: cover;
      background: #eef1f6;
      margin-right: 14px;
    }}
    .poster-placeholder {{
      display: flex;
      align-items: center;
      justify-content: center;
      color: #409eff;
      font-size: 17px;
      font-weight: 800;
    }}
    .content {{
      min-width: 0;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 5px;
    }}
    .topline {{
      display: flex;
      gap: 8px;
      align-items: flex-start;
      justify-content: space-between;
    }}
    .title {{
      color: #303133;
      font-size: 14px;
      line-height: 1.34;
      font-weight: 750;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .score {{
      min-width: 36px;
      color: #e800a4;
      font-size: 16px;
      line-height: 1.2;
      font-weight: 850;
      text-align: right;
    }}
    .badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .badge {{
      display: inline-block;
      max-width: 120px;
      padding: 2px 7px;
      border-radius: 6px;
      background: #f4f4f5;
      color: #909399;
      font-size: 11px;
      line-height: 1.4;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .badge.season {{
      background: #ecf5ff;
      color: #409eff;
    }}
    .badge.enabled {{
      background: #f0f9eb;
      color: #67c23a;
    }}
    .badge.progress {{
      background: #fdf6ec;
      color: #e6a23c;
    }}
    .badge.type {{
      background: #fef0f0;
      color: #f56c6c;
    }}
    .meta {{
      color: #909399;
      font-size: 12px;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .id {{
      color: #c0c4cc;
      font-size: 11px;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .empty {{
      padding: 22px 16px;
      color: #909399;
      text-align: center;
      border: 1px dashed #dcdfe6;
      border-radius: 8px;
      background: #fafafa;
    }}
    .footer {{
      padding: 10px 14px 13px 14px;
      color: #909399;
      font-size: 12px;
      border-top: 1px solid #ebeef5;
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="panel">
      <div class="header">
        <div class="header-left">
          {source_icon}
          <div class="title-block">
            <div class="eyebrow">ANI-RSS</div>
            <h1>{html.escape(heading)}</h1>
          </div>
        </div>
        <div class="summary">{html.escape(subtitle_text)}</div>
      </div>
      <div class="body">
        {sections_html}
      </div>
      <div class="footer">仅展示 ANI-RSS 中处于启用状态的订阅；下载、刷新与过滤仍由 ANI-RSS 处理。</div>
    </div>
  </div>
</body>
</html>"""


def parse_subscription_rows(body_lines: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_week = "未分组"
    for raw in body_lines:
        line = raw.strip()
        if not line:
            continue
        if _is_week_heading(line):
            current_week = line
            continue
        match = re.match(r"^(\d{1,2})\.\s+(.+)$", line)
        if match:
            rows.append(
                {
                    "index": match.group(1),
                    "title": match.group(2).strip(),
                    "week": current_week,
                },
            )
            continue
        if not rows or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        current = rows[-1]
        if key in {"集数", "progress"}:
            current["progress"] = value
        elif key in {"标签", "tags"}:
            current["tags"] = value
        elif key in {"评分", "score"}:
            current["score"] = value
        elif key in {"更新", "updated"}:
            current["updated"] = value
        elif key == "id":
            current["id"] = value
        elif key == "rss":
            current["rss"] = value
        elif key == "cover":
            current["cover"] = value
    return rows


def _render_week_section(
    week: str,
    rows: list[dict[str, str]],
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    cards = "\n".join(
        _render_subscription_row(row, cover_proxy=cover_proxy)
        for row in rows
    )
    return (
        '<section class="week-section">'
        f'<h2 class="week-title">{html.escape(week)}</h2>'
        f'<div class="grid">{cards}</div>'
        "</section>"
    )


def _render_subscription_row(
    row: dict[str, str],
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    title = row.get("title") or "(untitled)"
    index = row.get("index") or "?"
    score = row.get("score") or "-"
    progress = row.get("progress") or "-/*"
    tags = _split_tags(row.get("tags") or "")
    season = tags[0] if len(tags) > 0 else ""
    subgroup = tags[1] if len(tags) > 1 else ""
    media_type = tags[2] if len(tags) > 2 else ""
    updated = row.get("updated") or ""
    sub_id = row.get("id") or ""
    poster = _poster_html(row, cover_proxy=cover_proxy)

    badges = [
        _badge(season, "season"),
        _badge("已启用", "enabled"),
        _badge(progress, "progress"),
        _badge(media_type, "type"),
        _badge(subgroup, ""),
    ]
    badges_html = "".join(badge for badge in badges if badge)
    updated_html = f'<div class="meta">更新: {html.escape(updated)}</div>' if updated else ""
    id_html = f'<div class="id">ID: {html.escape(sub_id)}</div>' if sub_id else ""
    score_html = f'<div class="score">{html.escape(score)}</div>' if score != "-" else '<div class="score">-</div>'
    return (
        '<div class="sub-card">'
        f"{poster}"
        '<div class="content">'
        '<div class="topline">'
        f'<div class="title">{html.escape(title)}</div>'
        f"{score_html}"
        "</div>"
        f'<div class="badges">{badges_html}</div>'
        f"{updated_html}"
        f"{id_html}"
        "</div>"
        "</div>"
    )


def _group_rows(rows: list[dict[str, str]]) -> list[tuple[str, list[dict[str, str]]]]:
    groups: list[tuple[str, list[dict[str, str]]]] = []
    by_week: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        week = row.get("week") or "未分组"
        if week not in by_week:
            by_week[week] = []
            groups.append((week, by_week[week]))
        by_week[week].append(row)
    return groups


def _is_week_heading(line: str) -> bool:
    return bool(re.fullmatch(r"(?:星期[一二三四五六日天]|周[一二三四五六日天]|未分组)", line))


def _poster_html(
    row: dict[str, str],
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    src = cover_data_uri(row.get("cover") or "", cover_proxy=cover_proxy)
    title = row.get("title") or ""
    if src:
        return f'<img class="poster" src="{src}" alt="{html.escape(title)}">'
    label = html.escape(str(row.get("index") or "?")[:2])
    return f'<div class="poster-placeholder">{label}</div>'


def _badge(text: str, badge_class: str) -> str:
    clean = str(text or "").strip()
    if not clean or clean == "-":
        return ""
    class_text = f"badge {badge_class}".strip()
    return f'<span class="{html.escape(class_text)}">{html.escape(_short_text(clean, 16))}</span>'


def _split_tags(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split("/") if part.strip()]


def _short_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"
