from __future__ import annotations

import argparse
import importlib.util
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from preview_web_api import json_response

ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "web" / "page.py"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6181


def _dashboard_html() -> str:
    spec = importlib.util.spec_from_file_location("plana_web_page", PAGE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {PAGE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.dashboard_html("")


class PreviewHandler(BaseHTTPRequestHandler):
    html = _dashboard_html()

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/dashboard"}:
            self._send(HTTPStatus.OK, self.html.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._send_json(*json_response(parsed.path, parse_qs(parsed.query), {}))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            body = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            body = {}
        self._send_json(*json_response(parsed.path, parse_qs(parsed.query), body))

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 Plana Core 本地控制台预览。")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    host, port = server.server_address
    print(f"plana_web_preview=http://{host}:{port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
