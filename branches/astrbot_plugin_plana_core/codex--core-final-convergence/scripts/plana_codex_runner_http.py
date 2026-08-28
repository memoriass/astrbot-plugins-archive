#!/usr/bin/env python3
"""HTTP surface and process entry point for the Plana Codex Runner."""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import unquote
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Any

try:
    from plana_codex_runner_shim import (
        DEFAULT_ALLOWED_CLIENTS, DEFAULT_DATA_DIR, DEFAULT_HOST, DEFAULT_PORT,
        DEFAULT_WORKER_COUNTS, LANES, MAX_BODY_BYTES, LaneDisabledError,
        InvalidTaskPayloadError, RunnerState, _safe_int,
    )
except ModuleNotFoundError:
    from .plana_codex_runner_shim import (
        DEFAULT_ALLOWED_CLIENTS, DEFAULT_DATA_DIR, DEFAULT_HOST, DEFAULT_PORT,
        DEFAULT_WORKER_COUNTS, LANES, MAX_BODY_BYTES, LaneDisabledError,
        InvalidTaskPayloadError, RunnerState, _safe_int,
    )

class CodexRunnerHandler(BaseHTTPRequestHandler):
    server_version = "PlanaCodexRunner/1.0"

    @property
    def state(self) -> RunnerState:
        return self.server.state  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            payload = self.state.status()
            payload["data_dir"] = str(self.state.data_dir)
            self._send_json(HTTPStatus.OK, payload)
            return
        if self.path == "/status":
            if not self._authorized():
                return
            self._send_json(HTTPStatus.OK, self.state.status())
            return
        if self.path.startswith("/plana/codex/result/"):
            if not self._authorized():
                return
            run_id = self.path.rsplit("/", 1)[-1].strip()
            result = self.state.result(run_id)
            if result is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            else:
                self._send_json(HTTPStatus.OK, {"ok": True, "result": result})
            return
        if self.path.startswith("/plana/codex/artifact/"):
            if not self._authorized():
                return
            parts = self.path.split("?", 1)[0].rstrip("/").split("/")
            if len(parts) != 6:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
                return
            run_id = unquote(parts[-2]).strip()
            artifact_id = unquote(parts[-1]).strip()
            artifact = self.state.artifact(run_id, artifact_id)
            if artifact is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
                return
            path, metadata = artifact
            self._send_file(path, metadata)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/plana/codex/cancel/"):
            if not self._authorized():
                return
            run_id = self.path.rsplit("/", 1)[-1].strip()
            result = self.state.cancel(run_id)
            if result is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
                return
            status = str(result.get("status") or "")
            code = HTTPStatus.ACCEPTED if status == "cancelling" else HTTPStatus.OK
            self._send_json(code, {"ok": True, "status": status, "result": result})
            return
        if self.path != "/plana/codex/delegate":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self._authorized():
            return
        body = self._read_body()
        if body is None:
            return
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "payload_must_be_object"})
            return
        try:
            run_id, lane = self.state.enqueue(payload)
        except InvalidTaskPayloadError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": str(exc) or "invalid_task_payload"},
            )
            return
        except LaneDisabledError as exc:
            self._send_json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": "lane_disabled",
                    "lane": exc.lane,
                    "executes_tasks": self.state.ready,
                    "message": "The requested execution lane has no active workers.",
                },
            )
            return
        self._send_json(
            HTTPStatus.ACCEPTED,
            {
                "ok": True,
                "status": "queued",
                "run_id": run_id,
                "lane": lane,
                "runner": "plana-codex-runner",
                "engine": "codex",
                "executes_tasks": self.state.ready,
                "message": "Task queued by the Plana Codex runner.",
            },
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.log_date_time_string()} {self.client_address[0]} {fmt % args}", flush=True)

    def _authorized(self) -> bool:
        if not self._client_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "client_not_allowed"})
            return False
        expected = self.state.token
        if not expected:
            return True
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {expected}":
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def _client_allowed(self) -> bool:
        allowed = self.state.allowed_clients
        client = str(self.client_address[0] or "").strip()
        return bool(allowed) and any(_same_ip(client, item) for item in allowed)

    def _read_body(self) -> bytes | None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"ok": False, "error": "invalid_content_length"})
            return None
        if length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "empty_body"})
            return None
        if length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "body_too_large"})
            return None
        return self.rfile.read(length)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, metadata: dict[str, Any]) -> None:
        size = path.stat().st_size
        name = str(metadata.get("name") or path.name).replace('"', "_")
        self.send_response(int(HTTPStatus.OK))
        self.send_header("Content-Type", str(metadata.get("content_type") or "application/octet-stream"))
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("X-Plana-Artifact-Sha256", str(metadata.get("sha256") or ""))
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                self.wfile.write(chunk)


class CodexRunnerServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], state: RunnerState) -> None:
        super().__init__(address, CodexRunnerHandler)
        self.state = state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Plana Codex Runner.")
    parser.add_argument("--host", default=os.getenv("PLANA_CODEX_RUNNER_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("PLANA_CODEX_RUNNER_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--data-dir", default=os.getenv("PLANA_CODEX_RUNNER_DATA_DIR", DEFAULT_DATA_DIR))
    parser.add_argument("--token", default=os.getenv("PLANA_CODEX_RUNNER_TOKEN", ""))
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("PLANA_CODEX_TASK_TIMEOUT_SECONDS", "120")),
    )
    parser.add_argument(
        "--toolsets",
        default=os.getenv("PLANA_CODEX_TOOLSETS", "safe"),
    )
    parser.add_argument(
        "--allowed-clients",
        default=os.getenv("PLANA_CODEX_RUNNER_ALLOWED_CLIENTS", DEFAULT_ALLOWED_CLIENTS),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    allowed_clients = tuple(
        item.strip() for item in str(args.allowed_clients or "").split(",") if item.strip()
    )
    worker_counts = dict(DEFAULT_WORKER_COUNTS)
    raw_workers = os.getenv("PLANA_CODEX_WORKERS", "").strip()
    for item in raw_workers.split(","):
        lane, separator, raw_count = item.partition("=")
        lane = lane.strip()
        if not separator or lane not in worker_counts:
            continue
        worker_counts[lane] = max(0, min(_safe_int(raw_count, 0), 4))
    lane_toolsets: dict[str, str] = {}
    raw_lane_toolsets = os.getenv("PLANA_CODEX_LANE_TOOLSETS", "").strip()
    for item in raw_lane_toolsets.split(";"):
        lane, separator, value = item.partition("=")
        lane = lane.strip()
        if separator and lane in LANES and value.strip():
            lane_toolsets[lane] = value.strip()
    lane_timeouts: dict[str, int] = {}
    raw_lane_timeouts = os.getenv("PLANA_CODEX_LANE_TIMEOUTS", "").strip()
    for item in raw_lane_timeouts.split(","):
        lane, separator, value = item.partition("=")
        lane = lane.strip()
        if separator and lane in LANES:
            lane_timeouts[lane] = max(10, min(_safe_int(value, args.timeout_seconds), 3600))
    service_toolsets: dict[str, str] = {}
    raw_service_toolsets = os.getenv("PLANA_CODEX_SERVICE_TOOLSETS", "").strip()
    for item in raw_service_toolsets.split(";"):
        service_ref, separator, value = item.partition("=")
        service_ref = service_ref.strip()
        if separator and service_ref and value.strip():
            service_toolsets[service_ref] = value.strip()
    state = RunnerState(
        token=str(args.token),
        data_dir=Path(args.data_dir),
        allowed_clients=allowed_clients,
        timeout_seconds=args.timeout_seconds,
        toolsets=str(args.toolsets),
        worker_counts=worker_counts,
        lane_toolsets=lane_toolsets,
        lane_timeouts=lane_timeouts,
        service_toolsets=service_toolsets,
    )
    state.start_workers()
    server = CodexRunnerServer((str(args.host), int(args.port)), state)
    print(
        f"Plana Codex Runner listening on {args.host}:{args.port}; "
        f"data_dir={state.data_dir}; lanes={','.join(LANES)}; "
        f"workers={state.worker_counts}; executes_tasks={state.ready}; "
        f"allowed_clients={','.join(state.allowed_clients)}",
        flush=True,
    )
    server.serve_forever()


def _same_ip(left: str, right: str) -> bool:
    try:
        left_ip = ip_address(left)
        right_ip = ip_address(right)
    except ValueError:
        return left == right
    if left_ip.version == 6 and left_ip.ipv4_mapped is not None:
        left_ip = left_ip.ipv4_mapped
    if right_ip.version == 6 and right_ip.ipv4_mapped is not None:
        right_ip = right_ip.ipv4_mapped
    return left_ip == right_ip
