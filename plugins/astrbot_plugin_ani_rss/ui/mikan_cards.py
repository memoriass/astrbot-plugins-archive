from __future__ import annotations

import html
from typing import Any

from .media import source_icon_data_uri
from .blocks import (
    extract_heading,
    inline_markup,
)
from .mikan_rows import (
    mikan_scope_text,
    parse_mikan_rows,
    render_mikan_card_section,
)

MIKAN_CARD_HEADINGS = ("Mikan 搜索结果", "Mikan 推荐候选", "Mikan 选择要订阅的番剧")
MIKAN_SEARCH_HEADINGS = ("Mikan 搜索结果", "Mikan 选择要订阅的番剧")


def is_mikan_card_text(text: str, *, title: str = "") -> bool:
    lines = [line.rstrip() for line in str(text or "").strip().splitlines()]
    heading, _, _ = extract_heading(lines, title=title)
    return heading.startswith(MIKAN_CARD_HEADINGS)


def mikan_render_width(text: str, *, title: str = "", requested_width: int = 860) -> int:
    lines = [line.rstrip() for line in str(text or "").strip().splitlines()]
    heading, _, _ = extract_heading(lines, title=title)
    if heading.startswith("Mikan 推荐候选"):
        return 680
    if heading.startswith(MIKAN_SEARCH_HEADINGS):
        return 580
    return requested_width


def build_mikan_card_html(
    heading: str,
    subtitle: str,
    body_lines: list[str],
    *,
    cover_proxy: dict[str, Any] | None = None,
) -> str:
    if not heading.startswith(MIKAN_CARD_HEADINGS):
        return ""

    rows, notice, prompt = parse_mikan_rows(body_lines)
    if not rows:
        return ""

    scope = mikan_scope_text(heading, subtitle, rows)
    layout = "recommend" if heading.startswith("Mikan 推荐候选") else "search"
    section_html = render_mikan_card_section(
        scope,
        rows[:10],
        cover_proxy=cover_proxy,
        layout=layout,
    )
    notice_html = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""
    prompt_html = f'<div class="prompt">{inline_markup(prompt)}</div>' if prompt else ""
    subtitle_text = subtitle or f"{len(rows)} 项"
    eyebrow = "Mikan Search" if heading.startswith(MIKAN_SEARCH_HEADINGS) else "Mikan Recommend"
    source_icon = source_icon_data_uri([], heading)

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
      font-size: 15px;
      line-height: 1.45;
    }}
    .page {{
      padding: 8px;
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
      padding: 10px 12px 8px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #ebeef5;
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }}
    .source-icon {{
      flex: 0 0 42px;
      border-radius: 8px;
      background: #fff8df;
    }}
    .title-block {{
      min-width: 0;
    }}
    .eyebrow {{
      color: #409eff;
      font-size: 12px;
      font-weight: 700;
    }}
    h1 {{
      margin: 2px 0 0 0;
      color: #303133;
      font-size: 20px;
      line-height: 1.2;
      font-weight: 750;
    }}
    .summary {{
      color: #909399;
      font-size: 13px;
    }}
    .body {{
      padding: 8px 10px 10px 10px;
    }}
    .section {{
      margin-bottom: 10px;
    }}
    .section:last-child {{
      margin-bottom: 0;
    }}
    .section-title {{
      margin: 0 0 6px 0;
      font-size: 16px;
      line-height: 1.2;
      font-weight: 750;
      color: #111827;
    }}
    .grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: stretch;
      justify-content: flex-start;
    }}
    .grid.recommend .anime-card {{
      width: 316px;
      flex: 0 0 316px;
    }}
    .result-list {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .search-row {{
      position: relative;
      display: flex;
      gap: 14px;
      align-items: center;
      min-height: 122px;
      padding: 10px 80px 10px 10px;
      border: 1px solid #ebeef5;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 3px 8px rgba(31, 45, 61, 0.035);
    }}
    .search-row .anime-cover,
    .search-row .poster-placeholder {{
      width: 78px;
      height: 108px;
      border-radius: 6px;
      margin-right: 14px;
    }}
    .search-main {{
      min-width: 0;
      flex: 1;
      padding-left: 4px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 5px;
    }}
    .search-title {{
      color: #303133;
      font-size: 14px;
      line-height: 1.32;
      font-weight: 750;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .search-meta {{
      position: absolute;
      right: 16px;
      top: 39px;
      width: 56px;
      text-align: right;
    }}
    .search-meta .tag {{
      margin-top: 4px;
    }}
    .search-score {{
      display: inline-block;
      color: #e800a4;
      font-size: 12px;
      line-height: 1.25;
      font-weight: 800;
    }}
    .search-details {{
      color: #909399;
      font-size: 11px;
      line-height: 1.35;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .search-summary {{
      color: #606266;
      font-size: 12px;
      line-height: 1.38;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .search-index {{
      position: absolute;
      right: 9px;
      top: 9px;
      width: 24px;
      height: 24px;
      border-radius: 12px;
      background: #ecf5ff;
      color: #409eff;
      font-size: 12px;
      font-weight: 800;
      line-height: 24px;
      text-align: center;
    }}
    .anime-card {{
      position: relative;
      width: 100%;
      flex: 0 0 100%;
      min-height: 90px;
      display: flex;
      gap: 8px;
      padding: 7px;
      border: 1px solid #ebeef5;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 4px 10px rgba(31, 45, 61, 0.04);
    }}
    .anime-cover {{
      width: 54px;
      height: 76px;
      border-radius: 6px;
      object-fit: cover;
      flex: 0 0 auto;
      background: #e9edf4;
      margin-right: 8px;
    }}
    .poster-placeholder {{
      width: 54px;
      height: 76px;
      border-radius: 6px;
      flex: 0 0 auto;
      background: #f0f2f5;
      color: #909399;
      font-size: 18px;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 8px;
    }}
    .anime-main {{
      min-width: 0;
      flex: 1;
      padding-right: 24px;
    }}
    .index {{
      position: absolute;
      right: 7px;
      top: 7px;
      width: 20px;
      height: 20px;
      border-radius: 10px;
      background: #ecf5ff;
      color: #409eff;
      font-size: 12px;
      font-weight: 800;
      line-height: 20px;
      text-align: center;
    }}
    .anime-title {{
      margin: 1px 0 1px 0;
      color: #303133;
      font-size: 14px;
      line-height: 1.35;
      font-weight: 750;
    }}
    .score {{
      color: #e800a4;
      font-size: 17px;
      font-weight: 800;
      margin-bottom: 4px;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .tag {{
      display: inline-block;
      min-width: 42px;
      padding: 2px 6px;
      border-radius: 6px;
      background: #f4f4f5;
      color: #909399;
      font-size: 11px;
      line-height: 1.4;
      text-align: center;
    }}
    .tag.week {{
      background: #ecf5ff;
      color: #409eff;
    }}
    .tag.available {{
      background: #f0f9eb;
      color: #67c23a;
    }}
    .tag.subscribed {{
      background: #ecf5ff;
      color: #409eff;
    }}
    .notice {{
      margin-top: 8px;
      padding: 7px 9px;
      background: #f4f4f5;
      color: #909399;
      border-radius: 6px;
      font-size: 12px;
    }}
    .prompt {{
      margin-top: 8px;
      padding: 8px 10px;
      background: #ecf5ff;
      color: #337ecc;
      border: 1px solid #d9ecff;
      border-radius: 8px;
      font-weight: 600;
      font-size: 12px;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 7px;
      border-radius: 6px;
      background: #ecf5ff;
      color: #409eff;
      font-size: 12px;
      font-weight: 600;
      line-height: 1.35;
    }}
    .badge.success {{
      background: #f0f9eb;
      color: #67c23a;
    }}
    .badge.danger {{
      background: #fef0f0;
      color: #f56c6c;
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
            <div class="eyebrow">{html.escape(eyebrow)}</div>
            <h1>{html.escape(heading)}</h1>
          </div>
        </div>
        <div class="summary">{html.escape(subtitle_text)}</div>
      </div>
      <div class="body">
        {section_html}
        {notice_html}
        {prompt_html}
      </div>
    </div>
  </div>
</body>
</html>"""
