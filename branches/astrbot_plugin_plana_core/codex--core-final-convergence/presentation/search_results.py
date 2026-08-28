from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse


_PROCESS_MARKERS = (
    "\u5148\u770b\u4e00\u4e0b", "\u5148\u770b\u770b", "skill.md", "\u6ca1\u6709 shell",
    "\u6ca1\u6709shell", "run_shell", "web_search_searxng", "\u540e\u53f0\u8dd1",
    "\u540e\u53f0\u6267\u884c", "\u4ea4\u7ed9 hermes", "\u8f6c\u4ea4 hermes",
    "no shell", "use memory", "using memory", "\u9a6c\u4e0a\u67e5", "\u6b63\u5728\u67e5", "\u67e5\u8d77\u6765\u4e86",
)


def normalize_search_result(
    query: str,
    payload: Any,
    *,
    attempts: int,
    searched_at: str = "",
) -> dict[str, Any]:
    timestamp = searched_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: dict[str, Any] = {
        "contract_version": "plana.search.result.v1",
        "status": "invalid_response",
        "query": " ".join(str(query or "").split())[:300],
        "searched_at": timestamp,
        "source": "plana_search_gateway",
        "freshness": "live",
        "attempts": max(1, int(attempts or 1)),
        "items": [],
        "degraded_reason": "",
        "user_response_instruction": (
            "Use only these live search results. Cite source titles or URLs. "
            "Do not use memory, shell, skills, Hermes, or unsupported claims. "
            "Treat Mikan availability as unverified unless a result URL is from Mikan."
        ),
    }
    if not isinstance(payload, dict):
        result["degraded_reason"] = "payload_not_object"
        return result
    if payload.get("ok") is not True:
        result["status"] = "unavailable"
        result["degraded_reason"] = _clean(payload.get("error") or "search_unavailable", 120)
        return result
    rows = payload.get("results")
    if not isinstance(rows, list):
        result["degraded_reason"] = "results_not_list"
        return result
    items = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        title = _clean(row.get("title"), 240)
        url = _safe_http_url(row.get("url"))
        snippet = _clean(row.get("snippet"), 800)
        if not title or not url:
            continue
        host = str(urlparse(url).hostname or "").lower()
        score = _clean(row.get("score") or row.get("rating"), 80)
        score_source = _clean(row.get("score_source"), 160)
        items.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "source_host": host,
            "score": score or None,
            "score_source": score_source or (host if score else "unverified"),
            "mikan_status": "found" if _is_mikan_host(host) else "unverified",
        })
    result["items"] = items
    if not items:
        result["status"] = "empty"
        result["degraded_reason"] = "no_valid_results"
        return result
    result["status"] = "succeeded"
    return result


def search_query_from_message(message: str) -> str:
    clean = " ".join(str(message or "").split()).strip()
    lowered = clean.lower()
    for wake in ("plana", "\u666e\u62c9\u5a1c", "\u666e\u62c9\u7eb3"):
        if lowered.startswith(wake.lower()):
            clean = clean[len(wake):].lstrip(" \uff0c,\uff1a:")
            lowered = clean.lower()
            break
    for prefix in ("\u5e2e\u6211", "\u8bf7", "please"):
        if lowered.startswith(prefix.lower()):
            clean = clean[len(prefix):].lstrip(" \uff0c,\uff1a:")
            lowered = clean.lower()
            break
    for marker in ("\u641c\u4e00\u4e0b", "\u641c\u4e0b", "\u641c\u7d22", "\u68c0\u7d22", "\u67e5\u4e00\u4e0b", "\u67e5\u4e0b", "search"):
        index = lowered.find(marker.lower())
        if index >= 0:
            clean = clean[index + len(marker):].lstrip(" \uff0c,\uff1a:")
            break
    parts = [part.strip() for part in clean.replace("\uff0c", ",").split(",") if part.strip()]
    useful = [
        part for part in parts
        if not any(term in part.lower() for term in (
            "hermes", "\u53ea\u8bfb", "\u4e0d\u8981\u4ea4\u7ed9", "\u4e0d\u8981\u540e\u53f0", "\u7b80\u77ed\u7ed9",
        ))
    ]
    query = " ".join(useful) or clean
    now = datetime.now(timezone(timedelta(hours=8)))
    season = ("\u51ac\u5b63", "\u6625\u5b63", "\u590f\u5b63", "\u79cb\u5b63")[(now.month - 1) // 3]
    period = f"{now.year}\u5e74{((now.month - 1) // 3) * 3 + 1}\u6708 {season}"
    query = query.replace("\u8fd9\u5b63\u5ea6", period).replace("\u672c\u5b63\u5ea6", period).replace("\u5f53\u5b63", period)
    return " ".join(query.split())[:300]


def finalize_search_response(text: str, result: Any) -> str:
    if not isinstance(result, dict):
        return "\u5b9e\u65f6\u641c\u7d22\u7ed3\u679c\u4e0d\u53ef\u7528\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
    status = str(result.get("status") or "invalid_response")
    if status == "unavailable":
        return "\u5b9e\u65f6\u641c\u7d22\u670d\u52a1\u6682\u65f6\u4e0d\u53ef\u7528\uff0c\u6211\u6ca1\u6709\u4f7f\u7528\u5386\u53f2\u8bb0\u5fc6\u4ee3\u66ff\u6700\u65b0\u7ed3\u679c\u3002\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
    if status == "empty":
        return "\u5b9e\u65f6\u641c\u7d22\u5df2\u5b8c\u6210\uff0c\u4f46\u6ca1\u6709\u627e\u5230\u53ef\u6838\u9a8c\u7684\u7ed3\u679c\u3002\u53ef\u4ee5\u6362\u4e00\u4e2a\u5173\u952e\u8bcd\u540e\u91cd\u8bd5\u3002"
    if status != "succeeded":
        return "\u5b9e\u65f6\u641c\u7d22\u8fd4\u56de\u4e86\u65e0\u6cd5\u89e3\u6790\u7684\u6570\u636e\uff0c\u6211\u6ca1\u6709\u636e\u6b64\u751f\u6210\u63a8\u8350\u3002\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
    _ = text
    return _evidence_summary(result)


def search_result_is_renderable(query: str, result: Any) -> bool:
    if not isinstance(result, dict) or result.get("status") != "succeeded":
        return False
    if not explicitly_requests_card(query) and not _looks_like_recommendation(query):
        return False
    items = result.get("items")
    if not isinstance(items, list):
        return False
    minimum = 1 if explicitly_requests_card(query) else 3
    complete = [item for item in items if isinstance(item, dict)
                and str(item.get("title") or "").strip()
                and str(item.get("url") or "").strip()
                and str(item.get("source_host") or "").strip()]
    return len(complete) >= minimum


def explicitly_requests_card(query: str) -> bool:
    clean = " ".join(str(query or "").lower().split())
    return any(term in clean for term in ("\u5361\u7247", "\u56fe\u7247", "\u56fe\u8868", "\u914d\u56fe", "card", "image"))


def _looks_like_recommendation(query: str) -> bool:
    clean = " ".join(str(query or "").lower().split())
    return any(term in clean for term in ("\u63a8\u8350", "\u699c\u5355", "\u6392\u540d", "\u9ad8\u5206", "recommend", "ranking"))


def recommendation_card_document(query: str, result: Any) -> dict[str, Any] | None:
    if not search_result_is_renderable(query, result):
        return None
    rows = []
    for item in result.get("items", [])[:8]:
        if isinstance(item, dict):
            rows.append({
                "title": str(item.get("title") or "")[:160],
                "description": str(item.get("snippet") or item.get("source_host") or "")[:500],
                "status": "verified_source",
            })
    return {
        "contract_version": "plana.render.v1",
        "template": "list",
        "title": "\u5b9e\u65f6\u63a8\u8350\u5019\u9009",
        "status": "success",
        "summary": f"\u6765\u6e90\uff1a{result.get('source', 'live search')}\uff1b\u68c0\u7d22\u65f6\u95f4\uff1a{result.get('searched_at', '')}",
        "items": rows,
        "theme": "default",
        "density": "comfortable",
        "background": "transparent",
        "accent": "indigo",
        "icon": "list",
        "locale": "zh-CN",
        "privacy": "private",
        "footer": "\u56fe\u7247\u4e3a\u6587\u5b57\u7ed3\u679c\u7684\u8865\u5145\uff1b\u672a\u9a8c\u8bc1\u8bc4\u5206\u7684\u5019\u9009\u4e0d\u4ee3\u8868\u9ad8\u5206\u6392\u540d",
    }


def _strip_process_narration(text: str) -> str:
    lines = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if not line or any(marker in lowered for marker in _PROCESS_MARKERS):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _looks_like_search_failure(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in (
        "\u641c\u7d22\u4e0d\u53ef\u7528", "\u641c\u7d22\u5de5\u5177\u4e0d\u53ef\u7528",
        "\u65e0\u6cd5\u641c\u7d22", "\u641c\u7d22\u5931\u8d25", "\u6ca1\u6709\u641c\u7d22\u5de5\u5177",
        "search unavailable", "search failed",
    ))


def _evidence_summary(result: dict[str, Any]) -> str:
    items = [item for item in result.get("items", []) if isinstance(item, dict)]
    query = str(result.get("query") or "")
    recommendation = _looks_like_recommendation(query)
    mikan_related = "mikan" in query.lower() or "\u871c\u67d1" in query
    if not recommendation:
        lines = ["\u5b9e\u65f6\u641c\u7d22\u5df2\u5b8c\u6210\uff0c\u4ee5\u4e0b\u662f\u6309\u641c\u7d22\u540e\u7aef\u8fd4\u56de\u987a\u5e8f\u5217\u51fa\u7684\u524d\u4e09\u6761\u7ed3\u679c\uff1a"]
        for index, item in enumerate(items[:3], start=1):
            lines.extend((
                f"{index}. {item.get('title', '')}",
                f"   \u6765\u6e90\uff1a{item.get('source_host', '')}",
                f"   {item.get('url', '')}",
            ))
        searched_at = str(result.get("searched_at") or "")
        if searched_at:
            lines.append(f"\u68c0\u7d22\u65f6\u95f4\uff1a{searched_at}")
        return "\n".join(lines)
    has_verified_scores = any(
        item.get("score") and str(item.get("score_source") or "") != "unverified"
        for item in items[:3]
    )
    if has_verified_scores:
        lines = ["\u5b9e\u65f6\u641c\u7d22\u5df2\u5b8c\u6210\uff0c\u4ee5\u4e0b\u662f\u524d\u4e09\u4e2a\u53ef\u6838\u9a8c\u5019\u9009\uff1a"]
    else:
        lines = [
            "\u5b9e\u65f6\u641c\u7d22\u5df2\u5b8c\u6210\uff0c\u4f46\u7ed3\u679c\u7f3a\u5c11\u53ef\u6838\u9a8c\u8bc4\u5206\uff0c\u56e0\u6b64\u4e0d\u628a\u5b83\u4eec\u58f0\u79f0\u4e3a\u201c\u9ad8\u5206\u524d\u4e09\u540d\u201d\u3002",
            "\u4ee5\u4e0b\u4ec5\u6309\u641c\u7d22\u540e\u7aef\u8fd4\u56de\u987a\u5e8f\u5217\u51fa\u4e09\u4e2a\u5019\u9009\uff1a",
        ]
    for index, item in enumerate(items[:3], start=1):
        score = str(item.get("score") or "").strip()
        score_source = str(item.get("score_source") or "unverified").strip()
        score_text = f"{score}（{score_source}）" if score else "\u672a\u9a8c\u8bc1"
        row_lines = [
            f"{index}. {item.get('title', '')}",
            f"   \u8bc4\u5206\uff1a{score_text}",
            f"   \u6765\u6e90\uff1a{item.get('source_host', '')}",
        ]
        if mikan_related:
            mikan_text = "\u5df2\u627e\u5230 Mikan \u6765\u6e90" if item.get("mikan_status") == "found" else "\u672a\u9a8c\u8bc1"
            row_lines.append(f"   Mikan\uff1a{mikan_text}")
        row_lines.append(f"   {item.get('url', '')}")
        lines.extend(row_lines)
    searched_at = str(result.get("searched_at") or "")
    if searched_at:
        lines.append(f"\u68c0\u7d22\u65f6\u95f4\uff1a{searched_at}")
    if mikan_related:
        lines.append("Mikan \u72b6\u6001\u53ea\u6839\u636e\u5b9e\u65f6\u7ed3\u679c\u4e2d\u7684 Mikan \u9875\u9762\u5224\u5b9a\uff1b\u672a\u9a8c\u8bc1\u65f6\u4e0d\u58f0\u79f0\u5df2\u6709\u79cd\u5b50\u3002")
    return "\n".join(lines)


def _append_evidence_footer(text: str, result: dict[str, Any]) -> str:
    urls = [str(item.get("url") or "") for item in result.get("items", [])[:3]
            if isinstance(item, dict) and item.get("url")]
    missing = [url for url in urls if url not in text]
    footer = []
    if missing:
        footer.append("\u5b9e\u65f6\u6765\u6e90\uff1a")
        footer.extend(f"- {url}" for url in missing)
    found_mikan = any(str(item.get("mikan_status") or "") == "found"
                      for item in result.get("items", []) if isinstance(item, dict))
    if found_mikan:
        footer.append("Mikan \u72b6\u6001\uff1a\u5b9e\u65f6\u7ed3\u679c\u4e2d\u5b58\u5728 Mikan \u6765\u6e90\u3002")
    else:
        footer.append("Mikan \u72b6\u6001\uff1a\u672a\u9a8c\u8bc1\uff0c\u4e0d\u636e\u6b64\u58f0\u79f0\u5df2\u6709\u79cd\u5b50\u3002")
    searched_at = str(result.get("searched_at") or "")
    if searched_at:
        footer.append(f"\u68c0\u7d22\u65f6\u95f4\uff1a{searched_at}")
    return f"{text.rstrip()}\n\n" + "\n".join(footer)


def _safe_http_url(value: Any) -> str:
    url = str(value or "").strip()[:1000]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return url


def _is_mikan_host(host: str) -> bool:
    clean = str(host or "").lower().rstrip(".")
    return clean == "mikanani.me" or clean.endswith(".mikanani.me")


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]
