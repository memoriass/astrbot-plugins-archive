from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    for rel in (
        "metadata.yaml",
        "_conf_schema.json",
        "README.md",
        "main.py",
        "voice/__init__.py",
        "voice/external_api.py",
        "voice/runtime.py",
        "voice/audio_storage.py",
        "docs/voice_runtime_adr.md",
    ):
        require((ROOT / rel).is_file(), f"missing_file={rel}")
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    for key in (
        "enabled",
        "enable_core_api",
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
    ):
        require(key in schema, f"schema_key_missing={key}")
    require(
        schema["enabled"].get("default") is False,
        "tts_service_must_default_off",
    )
    require(
        schema["enable_core_api"].get("default") is False,
        "tts_core_api_must_default_off",
    )
    require(
        schema["external_api_enabled"].get("default") is False,
        "external_api_must_default_off",
    )
    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    require("from .voice import PlanaTTSPlugin" in main_py, "thin_entry_missing")
    runtime_py = (ROOT / "voice" / "runtime.py").read_text(encoding="utf-8")
    for snippet in (
        "PlanaTTSPlugin",
        '@filter.command("plana_tts")',
        '@filter.command("plana_tts_status")',
        "CONTRACT_VERSION",
        "plana.voice.synthesis.v1",
        "/plana_tts/synthesize",
        "/plana_tts/state",
        "def _is_loopback_request",
        "X-Forwarded-For",
        "local_loopback_only",
        "get_using_tts_provider",
        "Record.fromFileSystem",
        "SUPPORTED_ENGINES",
        "StarTools.get_data_dir",
        "_managed_audio_path",
        "shutil.copy2",
        "audio_root",
        "audio_ttl_seconds",
        "request_id",
        "duration_ms",
        "audio_bytes",
        "format_verified",
        "verification_level",
        "error_code",
        "error_stage",
        "retryable",
        "_cleanup_audio",
        "sovits_backend_boundary",
        "ExternalAPIClient",
        "external_api_enabled",
        "asyncio.Semaphore",
        "audio_storage.lease",
        "audio_quota_exceeded",
    ):
        require(snippet in runtime_py, f"runtime_missing={snippet}")
    for forbidden in (
        "self.api_token",
        '"api_token"',
        "X-Plana-TTS-Token",
        "request.headers.get(\"Authorization\"",
        "secrets",
    ):
        require(forbidden not in runtime_py, f"runtime_inline_auth_present={forbidden}")
    external_api_py = (ROOT / "voice" / "external_api.py").read_text(
        encoding="utf-8"
    )
    for snippet in (
        "class ExternalAPIClient",
        "external_api_disabled",
        "audio_base64",
        "audio_url",
        "audio_path",
        "Authorization",
        "_verify_audio_format",
        "external_api_audio_format_mismatch",
        "MAX_AUDIO_BYTES",
        "external_api_audio_url_not_allowed",
        "external_api_audio_path_outside_managed_root",
        "external_api_audio_too_large",
        "def _audio_url_allowed(",
        "request_id",
        "duration_ms",
        "audio_bytes",
        "format_verified",
        "_RejectRedirects",
        "_open_no_redirect",
    ):
        require(snippet in external_api_py, f"external_api_missing={snippet}")
    spaced_command = "plana" + " tts"
    require(
        f'@filter.command("{spaced_command}")' not in runtime_py,
        "spaced_command_leaked",
    )
    check_audio_storage()
    check_redirect_and_ssrf()
    print("tts_plugin_check=ok")


def check_audio_storage() -> None:
    from voice.audio_storage import AudioStorage

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        storage = AudioStorage(
            root, max_file_bytes=8, max_total_bytes=12,
            ttl_seconds=60, cleanup_interval_seconds=10,
        )
        old = root / "old.wav"
        old.write_bytes(b"1234")
        os.utime(old, (1, 1))
        with storage.lease(old):
            require(storage.cleanup(force=True) == 0, "leased_audio_deleted")
        require(storage.cleanup(force=True) == 1, "expired_audio_not_deleted")
        current = root / "current.wav"
        current.write_bytes(b"12345678")
        require(storage.ensure_capacity(8), "file_at_limit_rejected")
        overflow = root / "overflow.wav"
        overflow.write_bytes(b"12345")
        require(not storage.ensure_capacity(5), "directory_quota_not_enforced")
        require(not storage.ensure_capacity(9), "file_quota_not_enforced")


def check_redirect_and_ssrf() -> None:
    from voice.external_api import ExternalAPIClient, ExternalAPIConfig

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/private")
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A002, ANN001
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with tempfile.TemporaryDirectory() as tmp:
            client = ExternalAPIClient(
                ExternalAPIConfig(
                    True, f"http://127.0.0.1:{port}/tts", "", 2,
                    "text", "", "wav", {},
                ),
                Path(tmp),
            )
            require(
                not client._audio_url_allowed("http://localhost:9/private"),
                "cross_host_ssrf_allowed",
            )
            redirected = client._download_audio(
                f"http://127.0.0.1:{port}/redirect"
            )
            require(not redirected["ok"], "audio_redirect_followed")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
