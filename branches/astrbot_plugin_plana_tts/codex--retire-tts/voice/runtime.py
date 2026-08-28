from __future__ import annotations

import asyncio
import mimetypes
import shutil
from time import monotonic, time
import uuid
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Record
from astrbot.api.platform import MessageType
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.star.filter.command import GreedyStr
from quart import jsonify, request

from .external_api import ExternalAPIClient, _verify_audio_format
from .audio_storage import AudioStorage
from .core_service import PlanaTTSCoreService
from .core_server import PlanaTTSLoopbackServer


SUPPORTED_ENGINES = {"astrbot_provider", "external_api", "sovits"}
CONTRACT_VERSION = "plana.voice.synthesis.v1"


class PlanaTTSPlugin(Star):
    """Optional Plana-family TTS plugin."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = _normalize_config(config)
        self.enabled = bool(self.config.get("enabled", False))
        self.enable_core_api = bool(self.config.get("enable_core_api", False))
        self.engine = _engine(str(self.config.get("engine", "astrbot_provider") or ""))
        self.max_text_chars = _bounded_int(
            self.config.get("max_text_chars", 240),
            240,
            minimum=1,
            maximum=2000,
        )
        self.allow_group = bool(self.config.get("allow_group", True))
        self.allow_private = bool(self.config.get("allow_private", True))
        self.audio_dir = (
            Path(StarTools.get_data_dir("astrbot_plugin_plana_tts")) / "audio"
        )
        self.external_api = ExternalAPIClient.from_config(self.config, self.audio_dir)
        self.max_concurrency = _bounded_int(
            self.config.get("max_concurrency", 2), 2, minimum=1, maximum=16
        )
        self._synthesis_slots = asyncio.Semaphore(self.max_concurrency)
        self.audio_storage = AudioStorage(
            self.audio_dir,
            max_file_bytes=_bounded_int(
                self.config.get("max_audio_file_bytes", 20 * 1024 * 1024),
                20 * 1024 * 1024,
                minimum=1024,
                maximum=100 * 1024 * 1024,
            ),
            max_total_bytes=_bounded_int(
                self.config.get("max_audio_total_bytes", 256 * 1024 * 1024),
                256 * 1024 * 1024,
                minimum=1024,
                maximum=4 * 1024 * 1024 * 1024,
            ),
            ttl_seconds=_bounded_int(
                self.config.get("audio_ttl_seconds", 7 * 86400),
                7 * 86400,
                minimum=60,
                maximum=30 * 86400,
            ),
            cleanup_interval_seconds=_bounded_int(
                self.config.get("audio_cleanup_interval_seconds", 900),
                900,
                minimum=10,
                maximum=86400,
            ),
        )
        core_service = PlanaTTSCoreService(self, CONTRACT_VERSION)
        self.core_service = core_service if self.enable_core_api else None
        self.core_server = PlanaTTSLoopbackServer(
            core_service,
            enabled=(
                self.enabled
                and self.enable_core_api
                and bool(self.config.get("core_service_http_enabled", False))
            ),
            port=_bounded_int(
                self.config.get("core_service_port", 6191),
                6191,
                minimum=1024,
                maximum=65535,
            ),
            core_service_key=str(self.config.get("core_service_key", "") or ""),
        )

    async def initialize(self) -> None:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.audio_storage.cleanup(force=True)
        if self.enable_core_api:
            self.context.register_web_api(
                "/plana_tts/state",
                self.api_state,
                ["GET"],
                "Plana TTS state endpoint for Plana Core",
            )
            self.context.register_web_api(
                "/plana_tts/synthesize",
                self.api_synthesize,
                ["POST"],
                "Plana TTS synthesis endpoint for Plana Core",
            )
        if await self.core_server.start():
            logger.info(
                "Plana TTS loopback service started: http://127.0.0.1:%s",
                self.core_server.port,
            )
        logger.info("Plana TTS initialized: enabled=%s engine=%s", self.enabled, self.engine)

    async def terminate(self) -> None:
        await self.core_server.stop()
        logger.info("Plana TTS terminated")

    @filter.command("plana_tts")
    async def plana_tts(self, event: AstrMessageEvent, text: GreedyStr = ""):
        """Generate speech with the configured Plana TTS engine."""
        content = " ".join(str(text or "").split())
        error = self._validation_error(content, str(event.get_message_type()))
        if error:
            yield event.plain_result(self._command_error_text(error))
            return
        result = await self._synthesize_audio_limited(content, event.unified_msg_origin)
        if not result["ok"]:
            yield event.plain_result(f"TTS 生成失败：{result['error']}")
            return
        with self.audio_storage.lease(result["audio_path"]):
            yield event.result([Record.fromFileSystem(str(result["audio_path"]))])

    @filter.command("plana_tts_status")
    async def plana_tts_status(self, event: AstrMessageEvent):
        """Show Plana TTS runtime status."""
        yield event.plain_result(
            "Plana TTS\n"
            f"enabled={self.enabled}\n"
            f"core_api={self.enable_core_api}\n"
            f"engine={self.engine}\n"
            f"max_text_chars={self.max_text_chars}\n"
            f"allow_group={self.allow_group}\n"
            f"allow_private={self.allow_private}"
        )

    async def api_state(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify({"ok": True, "status": self._status_payload()})

    async def api_synthesize(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        contract_version = str(payload.get("contract_version") or "")
        if contract_version != CONTRACT_VERSION:
            return jsonify(
                {
                    "ok": False,
                    "error": "contract_version_mismatch",
                    "contract_version": CONTRACT_VERSION,
                }
            ), 400
        content = " ".join(str(payload.get("text") or "").split())
        error = self._validation_error(content, str(payload.get("message_type") or ""))
        if error:
            status = 403 if error in {"tts_disabled", "message_type_disabled"} else 400
            return jsonify(self._error_payload(error)), status
        result = await self._synthesize_audio_limited(
            content,
            str(payload.get("unified_msg_origin") or ""),
        )
        status = 200 if result["ok"] else 501
        return jsonify(result), status

    def _allowed_message_type(self, event: AstrMessageEvent) -> bool:
        message_type = event.get_message_type()
        if message_type == MessageType.GROUP_MESSAGE:
            return self.allow_group
        if message_type == MessageType.FRIEND_MESSAGE:
            return self.allow_private
        return True

    def _validation_error(self, content: str, message_type: str) -> str:
        if not self.enabled:
            return "tts_disabled"
        if not self._message_type_allowed(message_type):
            return "message_type_disabled"
        if not content:
            return "empty_text"
        if len(content) > self.max_text_chars:
            return "text_too_long"
        return ""

    def _message_type_allowed(self, message_type: str) -> bool:
        normalized = str(message_type or "").upper()
        if "GROUP" in normalized:
            return self.allow_group
        if "FRIEND" in normalized or "PRIVATE" in normalized:
            return self.allow_private
        return True

    async def _synthesize_audio(
        self, content: str, unified_msg_origin: str
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        started = monotonic()
        if self.engine == "astrbot_provider":
            provider = self.context.get_using_tts_provider(unified_msg_origin)
            if provider is None:
                return self._error_payload(
                    "astrbot_tts_provider_missing",
                    request_id=request_id,
                    started=started,
                )
            try:
                provider_audio_path = Path(str(await provider.get_audio(content))).resolve()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Plana TTS provider failed: %s", exc)
                return self._error_payload(
                    "provider_failed",
                    request_id=request_id,
                    started=started,
                )
            if not provider_audio_path.is_file():
                return self._error_payload(
                    "provider_audio_not_found",
                    request_id=request_id,
                    started=started,
                )
            try:
                audio_path = self._managed_audio_path(provider_audio_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Plana TTS audio copy failed: %s", exc)
                return self._error_payload(
                    "audio_copy_failed",
                    request_id=request_id,
                    started=started,
                )
            mime_type = mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"
            return self._success_payload(
                request_id=request_id,
                started=started,
                engine=self.engine,
                audio_path=audio_path,
                mime_type=mime_type,
            )
        if self.engine == "external_api":
            result = await self.external_api.synthesize(content)
            if not result.get("ok", False):
                return self._error_payload(
                    str(result.get("error") or "external_api_failed"),
                    request_id=str(result.get("request_id") or request_id),
                    started=started,
                    duration_ms=result.get("duration_ms"),
                )
            return {
                "ok": True,
                "contract_version": CONTRACT_VERSION,
                "source": "astrbot_plugin_plana_tts",
                "engine": self.engine,
                "audio_path": str(result.get("audio_path") or ""),
                "mime_type": str(result.get("mime_type") or "application/octet-stream"),
                "request_id": str(result.get("request_id") or request_id),
                "duration_ms": int(result.get("duration_ms") or 0),
                "audio_bytes": int(result.get("audio_bytes") or 0),
                "format_verified": bool(result.get("format_verified", False)),
            }
        return self._error_payload(
            f"engine_not_implemented:{self.engine}",
            request_id=request_id,
            started=started,
        )

    async def _synthesize_audio_limited(
        self, content: str, unified_msg_origin: str
    ) -> dict[str, Any]:
        self.audio_storage.cleanup()
        async with self._synthesis_slots:
            result = await self._synthesize_audio(content, unified_msg_origin)
        if result.get("ok"):
            audio_bytes = int(result.get("audio_bytes") or 0)
            if not self.audio_storage.ensure_capacity(audio_bytes):
                path = Path(str(result.get("audio_path") or ""))
                try:
                    if path.resolve().parent == self.audio_dir.resolve():
                        path.unlink(missing_ok=True)
                except OSError:
                    pass
                return self._error_payload("audio_quota_exceeded")
        return result

    def _status_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "core_api": self.enable_core_api,
            "contract_version": CONTRACT_VERSION,
            "engine": self.engine,
            "max_text_chars": self.max_text_chars,
            "allow_group": self.allow_group,
            "allow_private": self.allow_private,
            "implemented_engines": ["astrbot_provider", "external_api"],
            "planned_engines": ["sovits"],
            "external_api": self.external_api.status(),
            "source_controlled_by_plugin": True,
            "local_loopback_only": True,
            "audio_root": str(self.audio_dir),
            "audio_ttl_seconds": self.audio_storage.ttl_seconds,
            "audio_total_bytes": self.audio_storage.total_bytes(),
            "audio_total_quota_bytes": self.audio_storage.max_total_bytes,
            "max_concurrency": self.max_concurrency,
            "sovits_backend_boundary": "plugin_engine_only",
        }

    def _success_payload(
        self,
        *,
        request_id: str,
        started: float,
        engine: str,
        audio_path: Path,
        mime_type: str,
    ) -> dict[str, Any]:
        data = audio_path.read_bytes()
        verified = _verify_audio_format(data, mime_type, audio_path.suffix.lstrip("."))
        if not data:
            return self._error_payload(
                "empty_audio",
                request_id=request_id,
                started=started,
            )
        if not verified:
            return self._error_payload(
                "audio_format_mismatch",
                request_id=request_id,
                started=started,
            )
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "source": "astrbot_plugin_plana_tts",
            "engine": engine,
            "audio_path": str(audio_path),
            "mime_type": mime_type,
            "request_id": request_id,
            "duration_ms": int((monotonic() - started) * 1000),
            "audio_bytes": len(data),
            "format_verified": verified,
        }

    def _error_payload(
        self,
        error: str,
        *,
        request_id: str = "",
        started: float | None = None,
        duration_ms: object = None,
    ) -> dict[str, Any]:
        if duration_ms is None and started is not None:
            duration_ms = int((monotonic() - started) * 1000)
        return {
            "ok": False,
            "contract_version": CONTRACT_VERSION,
            "source": "astrbot_plugin_plana_tts",
            "engine": self.engine,
            "error": error,
            "request_id": request_id,
            "duration_ms": int(duration_ms or 0),
            "audio_bytes": 0,
            "format_verified": False,
            "verification_level": "none",
            "error_code": str(error or "tts_failed").split(":", 1)[0],
            "error_stage": "runtime",
            "retryable": False,
        }

    def _command_error_text(self, error: str) -> str:
        if error == "tts_disabled":
            return "Plana TTS 已禁用。"
        if error == "message_type_disabled":
            return "当前会话类型未启用 Plana TTS。"
        if error == "empty_text":
            return "用法：/plana_tts <要朗读的文字>"
        if error == "text_too_long":
            return f"文本过长：最多 {self.max_text_chars} 字。"
        return f"TTS 不可用：{error}"

    def _authorized(self) -> bool:
        return self._is_loopback_request()

    def _is_loopback_request(self) -> bool:
        forwarded_headers = ("X-Forwarded-For", "X-Real-IP", "Forwarded")
        if any(request.headers.get(name, "").strip() for name in forwarded_headers):
            return False
        remote = str(request.remote_addr or "").strip().lower()
        return (
            remote in {"127.0.0.1", "::1", "localhost"}
            or remote.startswith("::ffff:127.")
        )

    def _managed_audio_path(self, provider_audio_path: Path) -> Path:
        audio_root = self.audio_dir.resolve()
        provider_audio_path = provider_audio_path.resolve()
        try:
            provider_audio_path.relative_to(audio_root)
            return provider_audio_path
        except ValueError:
            pass
        suffix = provider_audio_path.suffix.lower()
        if suffix not in {".wav", ".mp3", ".ogg", ".opus", ".flac", ".m4a", ".aac"}:
            suffix = ".audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        target = self.audio_dir / f"{uuid.uuid4().hex}{suffix}"
        shutil.copy2(provider_audio_path, target)
        return target

    def _cleanup_audio(self, *, max_age_seconds: int) -> int:
        cutoff = time() - max(3600, int(max_age_seconds or 0))
        removed = 0
        for path in self.audio_dir.glob("*"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed


def _normalize_config(config: Any) -> dict[str, Any]:
    getter = getattr(config, "get", None)
    if not callable(getter):
        return {}
    keys = [
        "enabled",
        "enable_core_api",
        "core_service_http_enabled",
        "core_service_port",
        "core_service_key",
        "engine",
        "max_text_chars",
        "allow_group",
        "allow_private",
        "external_api_enabled",
        "external_api_url",
        "external_api_token",
        "external_api_timeout_seconds",
        "external_api_text_key",
        "external_api_voice",
        "external_api_format",
        "external_api_extra_payload",
        "sovits_base_url",
        "max_concurrency",
        "max_audio_file_bytes",
        "max_audio_total_bytes",
        "audio_ttl_seconds",
        "audio_cleanup_interval_seconds",
    ]
    return {key: getter(key) for key in keys if getter(key) is not None}


def _engine(value: str) -> str:
    normalized = value.strip().lower() or "astrbot_provider"
    return normalized if normalized in SUPPORTED_ENGINES else "astrbot_provider"


def _bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))
