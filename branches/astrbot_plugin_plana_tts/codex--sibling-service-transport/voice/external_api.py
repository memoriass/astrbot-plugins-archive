from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from time import monotonic
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from urllib.parse import urlparse
from uuid import uuid4


MAX_AUDIO_BYTES = 20 * 1024 * 1024


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass
class ExternalAPIConfig:
    enabled: bool
    url: str
    token: str
    timeout_seconds: int
    text_key: str
    voice: str
    audio_format: str
    extra_payload: dict[str, Any]


class ExternalAPIClient:
    """Generic external TTS HTTP client.

    Supports common API shapes:
    - binary audio response
    - JSON with local ``audio_path``
    - JSON with ``audio_base64``
    - JSON with ``audio_url``
    """

    def __init__(self, config: ExternalAPIConfig, output_dir: Path) -> None:
        self.config = config
        self.output_dir = output_dir

    @classmethod
    def from_config(cls, config: dict[str, Any], output_dir: Path) -> "ExternalAPIClient":
        return cls(
            ExternalAPIConfig(
                enabled=_bool(config.get("external_api_enabled", False)),
                url=str(config.get("external_api_url", "") or "").strip(),
                token=str(config.get("external_api_token", "") or "").strip(),
                timeout_seconds=max(
                    1,
                    min(
                        int(config.get("external_api_timeout_seconds", 20) or 20),
                        120,
                    ),
                ),
                text_key=str(config.get("external_api_text_key", "text") or "text"),
                voice=str(config.get("external_api_voice", "") or "").strip(),
                audio_format=_format(config.get("external_api_format", "wav")),
                extra_payload=_json_object(
                    str(config.get("external_api_extra_payload", "") or "")
                ),
            ),
            output_dir,
        )

    async def synthesize(self, text: str) -> dict[str, Any]:
        request_id = uuid4().hex
        started = monotonic()
        if not self.config.enabled:
            result = self._error("external_api_disabled")
            return self._with_metadata(result, request_id, started)
        if not self.config.url:
            result = self._error("external_api_url_missing")
            return self._with_metadata(result, request_id, started)
        result = await asyncio.to_thread(self._synthesize_sync, text)
        return self._with_metadata(result, request_id, started)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "configured": bool(self.config.url),
            "text_key": self.config.text_key,
            "voice_configured": bool(self.config.voice),
            "format": self.config.audio_format,
            "timeout_seconds": self.config.timeout_seconds,
        }

    def _synthesize_sync(self, text: str) -> dict[str, Any]:
        payload = dict(self.config.extra_payload)
        payload[self.config.text_key] = text
        if self.config.voice:
            payload.setdefault("voice", self.config.voice)
        if self.config.audio_format:
            payload.setdefault("format", self.config.audio_format)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Accept": "application/json,audio/*;q=0.9,application/octet-stream;q=0.8",
            "Content-Type": "application/json; charset=utf-8",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        request = Request(self.config.url, data=body, headers=headers, method="POST")
        try:
            with _open_no_redirect(request, self.config.timeout_seconds) as response:
                data = response.read(MAX_AUDIO_BYTES + 1)
                content_type = str(response.headers.get("Content-Type", ""))
        except HTTPError as exc:
            detail = _short_error(exc.read())
            return self._error(f"external_api_http_{exc.code}:{detail}")
        except URLError as exc:
            return self._error(f"external_api_unreachable:{exc.reason}")
        except TimeoutError:
            return self._error("external_api_timeout")
        except Exception as exc:  # noqa: BLE001
            return self._error(f"external_api_failed:{str(exc)[:120]}")
        if len(data) > MAX_AUDIO_BYTES:
            return self._error("external_api_response_too_large", stage="response")
        return self._response_to_audio(data, content_type)

    def _response_to_audio(self, data: bytes, content_type: str) -> dict[str, Any]:
        mime_type = _mime(content_type)
        if not data:
            return self._error("external_api_empty_response")
        if "json" in mime_type or data[:1] in {b"{", b"["}:
            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._error("external_api_invalid_json")
            if not isinstance(payload, dict):
                return self._error("external_api_invalid_json")
            return self._json_to_audio(payload)
        return self._save_audio(data, mime_type or "application/octet-stream")

    def _json_to_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        audio_path = str(
            payload.get("audio_path")
            or payload.get("file_path")
            or payload.get("path")
            or ""
        ).strip()
        if audio_path:
            path = Path(audio_path).resolve()
            try:
                path.relative_to(self.output_dir.resolve())
            except ValueError:
                return self._error("external_api_audio_path_outside_managed_root", stage="decode")
            if path.is_file():
                mime_type = (
                    _mime(str(payload.get("mime_type") or ""))
                    or mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream"
                )
                return self._save_audio(path.read_bytes(), mime_type)
            return self._error("external_api_audio_path_not_found")
        audio_url = str(payload.get("audio_url") or payload.get("url") or "").strip()
        if audio_url:
            if not self._audio_url_allowed(audio_url):
                return self._error("external_api_audio_url_not_allowed", stage="download")
            return self._download_audio(audio_url)
        audio_base64 = str(
            payload.get("audio_base64") or payload.get("audio") or ""
        ).strip()
        if audio_base64:
            return self._base64_to_audio(
                audio_base64,
                _mime(str(payload.get("mime_type") or "")),
            )
        if payload.get("ok") is False:
            return self._error(str(payload.get("error") or "external_api_not_ok"))
        return self._error("external_api_missing_audio")

    def _download_audio(self, url: str) -> dict[str, Any]:
        headers = {"Accept": "audio/*,application/octet-stream;q=0.8"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        request = Request(url, headers=headers, method="GET")
        try:
            with _open_no_redirect(request, self.config.timeout_seconds) as response:
                data = response.read(MAX_AUDIO_BYTES + 1)
                content_type = str(response.headers.get("Content-Type", ""))
        except Exception as exc:  # noqa: BLE001
            return self._error(f"external_api_audio_download_failed:{str(exc)[:120]}")
        if len(data) > MAX_AUDIO_BYTES:
            return self._error("external_api_audio_too_large", stage="download")
        return self._save_audio(data, _mime(content_type) or "application/octet-stream")

    def _base64_to_audio(self, value: str, mime_type: str) -> dict[str, Any]:
        raw = value
        if value.startswith("data:") and "," in value:
            header, raw = value.split(",", 1)
            mime_type = _mime(header.removeprefix("data:").split(";", 1)[0]) or mime_type
        if len(raw) > ((MAX_AUDIO_BYTES * 4) // 3) + 16:
            return self._error("external_api_audio_too_large", stage="decode")
        try:
            data = base64.b64decode(raw, validate=True)
        except Exception:  # noqa: BLE001
            return self._error("external_api_invalid_base64")
        return self._save_audio(data, mime_type or "application/octet-stream")

    def _save_audio(self, data: bytes, mime_type: str) -> dict[str, Any]:
        if not data:
            return self._error("external_api_empty_audio")
        if len(data) > MAX_AUDIO_BYTES:
            return self._error("external_api_audio_too_large", stage="save")
        verified = _verify_audio_format(data, mime_type, self.config.audio_format)
        if not verified:
            return self._error("external_api_audio_format_mismatch")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        extension = _extension(mime_type, self.config.audio_format)
        path = self.output_dir / f"external_{uuid4().hex}{extension}"
        path.write_bytes(data)
        return {
            "ok": True,
            "audio_path": str(path),
            "mime_type": mime_type or "application/octet-stream",
            "audio_bytes": len(data),
            "format_verified": verified,
            "verification_level": "header_only",
        }

    def _error(
        self,
        error: str,
        *,
        stage: str = "backend",
        retryable: bool | None = None,
    ) -> dict[str, Any]:
        code = str(error or "external_api_failed").split(":", 1)[0]
        if retryable is None:
            retryable = code in {
                "external_api_timeout",
                "external_api_unreachable",
                "external_api_audio_download_failed",
            } or code.startswith("external_api_http_5")
        return {
            "ok": False,
            "error": str(error or code)[:300],
            "error_code": code,
            "error_stage": stage,
            "retryable": bool(retryable),
        }

    def _with_metadata(
        self,
        result: dict[str, Any],
        request_id: str,
        started: float,
    ) -> dict[str, Any]:
        result["request_id"] = request_id
        result["duration_ms"] = int((monotonic() - started) * 1000)
        result.setdefault("audio_bytes", 0)
        result.setdefault("format_verified", False)
        result.setdefault("verification_level", "none")
        result.setdefault("error_code", "")
        result.setdefault("error_stage", "")
        result.setdefault("retryable", False)
        return result

    def _audio_url_allowed(self, url: str) -> bool:
        candidate = urlparse(str(url or "").strip())
        configured = urlparse(self.config.url)
        return bool(
            candidate.scheme in {"http", "https"}
            and not candidate.username
            and not candidate.password
            and candidate.hostname
            and configured.hostname
            and candidate.hostname.lower() == configured.hostname.lower()
        )


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _open_no_redirect(request: Request, timeout: int):
    return build_opener(_RejectRedirects).open(request, timeout=timeout)


def _format(value: Any) -> str:
    text = str(value or "wav").strip().lower().lstrip(".")
    return text if text in {"wav", "mp3", "ogg", "opus", "m4a", "flac"} else "wav"


def _json_object(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _mime(content_type: str) -> str:
    return str(content_type or "").split(";", 1)[0].strip().lower()


def _extension(mime_type: str, fallback_format: str) -> str:
    guessed = mimetypes.guess_extension(_mime(mime_type))
    if guessed:
        return guessed
    return f".{_format(fallback_format)}"


def _verify_audio_format(
    data: bytes,
    mime_type: str,
    fallback_format: str = "",
) -> bool:
    fmt = _format_from_mime(mime_type) or _format(fallback_format)
    if fmt == "wav":
        return data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    if fmt == "mp3":
        return data.startswith(b"ID3") or data[:1] == b"\xff"
    if fmt in {"ogg", "opus"}:
        return data.startswith(b"OggS")
    if fmt == "flac":
        return data.startswith(b"fLaC")
    if fmt == "m4a":
        return b"ftyp" in data[:16]
    return bool(data)


def _format_from_mime(mime_type: str) -> str:
    clean = _mime(mime_type)
    if clean in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return "wav"
    if clean in {"audio/mpeg", "audio/mp3"}:
        return "mp3"
    if clean in {"audio/ogg", "application/ogg"}:
        return "ogg"
    if clean == "audio/flac":
        return "flac"
    if clean in {"audio/mp4", "audio/x-m4a"}:
        return "m4a"
    return ""


def _short_error(data: bytes) -> str:
    try:
        return data[:200].decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
