from __future__ import annotations

import html


def extract_heading(lines: list[str], *, title: str = "") -> tuple[str, str, list[str]]:
    if title:
        return title, "", lines
    if not lines:
        return "ANI-RSS", "", []
    first = lines[0].strip()
    heading = first
    subtitle = ""
    if ":" in first:
        heading, subtitle = first.split(":", 1)
        heading = heading.strip() or "ANI-RSS"
        subtitle = subtitle.strip()
    return heading, subtitle, lines[1:]


def render_blocks(lines: list[str]) -> str:
    html_blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if _is_table_start(lines, index):
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines):
                current = lines[index].strip()
                if current.startswith("|"):
                    table_lines.append(lines[index])
                    index += 1
                    continue
                if current.startswith(("http://", "https://")):
                    index += 1
                    continue
                break
            html_blocks.append(_render_table(table_lines))
            continue
        if line.startswith("回复"):
            html_blocks.append(f'<div class="prompt">{html.escape(line)}</div>')
        elif line.startswith("评分来自") or line.startswith("当前预览"):
            html_blocks.append(f'<div class="notice">{html.escape(line)}</div>')
        elif line.startswith(("http://", "https://", "rss:")):
            html_blocks.append(f'<div class="url">{breakable_url_markup(line)}</div>')
        elif line.startswith(("sample:", "示例:")):
            html_blocks.append(f'<div class="sample">{inline_markup(line)}</div>')
        elif line.startswith(("下载路径:", "路径:")):
            html_blocks.append(f'<div class="path">{inline_markup(line)}</div>')
        elif _looks_numbered(line):
            html_blocks.append(_render_numbered_line(line))
        else:
            html_blocks.append(f'<div class="line">{inline_markup(line)}</div>')
        index += 1
    return "\n".join(html_blocks)


def inline_markup(text: str) -> str:
    escaped = html.escape(text)
    classes = {
        "可订阅": "success",
        "已订阅": "info",
        "enabled": "success",
        "disabled": "info",
        "已启用": "success",
        "未启用": "info",
        "添加订阅成功": "success",
        "确认": "success",
        "取消": "danger",
        "简中": "success",
        "简繁": "warning",
    }
    for word, badge_class in classes.items():
        escaped = escaped.replace(
            html.escape(word),
            f'<span class="badge {badge_class}">{html.escape(word)}</span>',
        )
    return escaped


def breakable_text(text: str, *, chunk_size: int = 18) -> str:
    parts: list[str] = []
    run = 0
    for char in str(text or ""):
        parts.append(html.escape(char))
        run += 1
        if char in "/?&=-_.#%" or run >= chunk_size:
            parts.append("<wbr>")
            run = 0
    return "".join(parts)


def breakable_url_markup(text: str) -> str:
    clean = str(text or "").strip()
    if clean.lower().startswith("rss:"):
        label, _, url = clean.partition(":")
        url = url.strip()
        if not url:
            return html.escape(clean)
        return (
            f'<span class="url-label">{html.escape(label)}:</span><br>'
            f'<span class="url-text">{breakable_text(url)}</span>'
        )
    return f'<span class="url-text">{breakable_text(clean)}</span>'


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return lines[index].strip().startswith("|") and set(lines[index + 1].strip()) <= {
        "|",
        "-",
        ":",
        " ",
    }


def _render_table(lines: list[str]) -> str:
    header = _split_table_row(lines[0])
    rows = [_split_table_row(line) for line in lines[2:]]
    header_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    row_html = []
    for row in rows:
        cells = []
        for idx, cell in enumerate(row):
            cls = ""
            if idx == 0:
                cls = ' class="num"'
            elif idx == 1:
                cls = ' class="score"'
            cells.append(f"<td{cls}>{_table_cell(cell)}</td>")
        row_html.append("<tr>" + "".join(cells) + "</tr>")
    return "<table><thead><tr>" + header_html + "</tr></thead><tbody>" + "".join(row_html) + "</tbody></table>"


def _split_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def _looks_numbered(line: str) -> bool:
    prefix, _, rest = line.partition(".")
    return bool(rest.strip()) and prefix.isdigit()


def _render_numbered_line(line: str) -> str:
    prefix, _, rest = line.partition(".")
    return (
        '<div class="item-row">'
        f'<span class="item-index">{html.escape(prefix)}</span>'
        f'<div class="item-text">{inline_markup(rest.strip())}</div></div>'
    )


def _table_cell(text: str) -> str:
    if text == "可订阅":
        return '<span class="badge success">可订阅</span>'
    if text == "已订阅":
        return '<span class="badge info">已订阅</span>'
    if text in {"enabled", "已启用"}:
        return f'<span class="badge success">{html.escape(text)}</span>'
    if text in {"disabled", "未启用"}:
        return f'<span class="badge info">{html.escape(text)}</span>'
    return inline_markup(text)
