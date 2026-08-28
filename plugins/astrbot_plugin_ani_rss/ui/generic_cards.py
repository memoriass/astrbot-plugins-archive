from __future__ import annotations

import html

from .blocks import extract_heading, render_blocks
from .media import source_icon_data_uri

SUCCESS_CARD_HEADINGS = ("ANI-RSS 添加订阅成功",)


def is_success_card_text(text: str, *, title: str = "") -> bool:
    lines = [line.rstrip() for line in str(text or "").strip().splitlines()]
    heading, _, _ = extract_heading(lines, title=title)
    return heading.startswith(SUCCESS_CARD_HEADINGS)


def build_generic_card_html(
    lines: list[str],
    heading: str,
    subtitle: str,
    body_lines: list[str],
) -> str:
    blocks = render_blocks(body_lines)
    icon = source_icon_data_uri(lines, heading)
    footer = (
        "订阅已提交；后续状态以 ANI-RSS 为准。"
        if heading.startswith(SUCCESS_CARD_HEADINGS)
        else "交互完成、取消或超时后会自动清理本次生成的临时卡片。"
    )
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
      line-height: 1.55;
    }}
    .page {{
      padding: 22px;
      width: 100%;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #ebeef5;
      border-radius: 12px;
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.04);
      overflow: hidden;
    }}
    .header {{
      padding: 18px 22px 14px 22px;
      border-bottom: 1px solid #ebeef5;
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .source-icon {{
      width: 42px;
      height: 42px;
      border-radius: 12px;
      background: #ecf5ff;
      border: 1px solid #d9ecff;
      padding: 7px;
      object-fit: contain;
    }}
    .header-text {{
      min-width: 0;
      flex: 1;
    }}
    .eyebrow {{
      color: #409eff;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    h1 {{
      margin: 3px 0 2px 0;
      font-size: 24px;
      line-height: 1.25;
      font-weight: 650;
      color: #303133;
    }}
    .subtitle {{
      color: #909399;
      font-size: 14px;
    }}
    .body {{
      padding: 18px 22px 20px 22px;
    }}
    p {{
      margin: 8px 0;
    }}
    .notice {{
      margin-top: 10px;
      padding: 10px 12px;
      background: #f4f4f5;
      border: 1px solid #e9e9eb;
      border-radius: 8px;
      color: #606266;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .prompt {{
      margin-top: 12px;
      padding: 10px 12px;
      background: #ecf5ff;
      border: 1px solid #d9ecff;
      border-radius: 8px;
      color: #337ecc;
      font-weight: 650;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      margin-bottom: 10px;
      border: 1px solid #ebeef5;
      border-radius: 8px;
      overflow: hidden;
    }}
    th {{
      background: #f5f7fa;
      color: #606266;
      text-align: left;
      font-weight: 650;
      padding: 10px 12px;
      border-bottom: 1px solid #ebeef5;
    }}
    td {{
      padding: 10px 12px;
      border-bottom: 1px solid #ebeef5;
      vertical-align: top;
    }}
    tbody tr:nth-child(even) {{
      background: #fafafa;
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    .num {{
      color: #409eff;
      font-weight: 650;
      white-space: nowrap;
    }}
    .score {{
      color: #e800a4;
      font-weight: 750;
      white-space: nowrap;
    }}
    .muted {{
      color: #909399;
      font-size: 13px;
    }}
    .line {{
      padding: 8px 0;
      border-bottom: 1px solid #f2f6fc;
      color: #606266;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .line:last-child {{
      border-bottom: none;
    }}
    .url {{
      margin: 4px 0 8px 0;
      color: #909399;
      font-size: 12px;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .url-label {{
      color: #909399;
      font-weight: 650;
    }}
    .url-text {{
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .sample {{
      padding: 5px 0;
      color: #606266;
      font-size: 13px;
      overflow-wrap: anywhere;
      word-break: break-word;
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
    .badge.info {{
      background: #f4f4f5;
      color: #909399;
    }}
    .badge.warning {{
      background: #fdf6ec;
      color: #e6a23c;
    }}
    .badge.danger {{
      background: #fef0f0;
      color: #f56c6c;
    }}
    .path {{
      color: #606266;
      background: #f5f7fa;
      border-radius: 8px;
      padding: 8px 10px;
      margin: 8px 0;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .item-row {{
      display: flex;
      gap: 8px;
      align-items: flex-start;
      padding: 8px 0;
      border-bottom: 1px solid #f2f6fc;
    }}
    .item-row:last-child {{
      border-bottom: none;
    }}
    .item-index {{
      display: inline-block;
      min-width: 22px;
      height: 22px;
      line-height: 22px;
      text-align: center;
      border-radius: 50%;
      background: #ecf5ff;
      color: #409eff;
      font-size: 12px;
      font-weight: 650;
      flex: 0 0 auto;
    }}
    .item-text {{
      flex: 1;
      min-width: 0;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .footer {{
      padding: 11px 22px 15px 22px;
      color: #909399;
      font-size: 12px;
      border-top: 1px solid #ebeef5;
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="card">
      <div class="header">
        {icon}
        <div class="header-text">
          <div class="eyebrow">ANI-RSS</div>
          <h1>{html.escape(heading)}</h1>
          <div class="subtitle">{html.escape(subtitle)}</div>
        </div>
      </div>
      <div class="body">
        {blocks}
      </div>
      <div class="footer">{html.escape(footer)}</div>
    </div>
  </div>
</body>
</html>"""
