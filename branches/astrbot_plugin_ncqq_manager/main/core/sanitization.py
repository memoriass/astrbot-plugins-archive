"""Shared text masking helpers for user-visible output."""

from __future__ import annotations

import re

_SECRET_NAMES = (
    "token",
    "api_key",
    "api-key",
    "apikey",
    "password",
    "passwd",
    "pwd",
    "secret",
    "cookie",
    "authorization",
    "access_token",
    "access-token",
    "refresh_token",
    "refresh-token",
)

_SECRET_KV_RE = re.compile(
    r"(?i)([\"']?\b(?:"
    + "|".join(re.escape(name) for name in _SECRET_NAMES)
    + r")\b[\"']?\s*[:=]\s*)([\"']?)[^\"'\s,;&}]+([\"']?)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def sanitize_text(value: object, *, max_length: int | None = None) -> str:
    text = str(value or "")
    text = _SECRET_KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***{m.group(3)}", text)
    text = _BEARER_RE.sub("Bearer ***", text)
    text = _OPENAI_KEY_RE.sub("sk-***", text)
    if max_length is not None and len(text) > max_length:
        return text[: max(0, max_length - 3)] + "..."
    return text
