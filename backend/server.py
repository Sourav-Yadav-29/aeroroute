"""Local HTTP server for the AeroRoute educational app."""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

try:
    from .cli import load_scenario, _write_scenario
    from .planner import plan, validate_scenario
except ImportError:  # pragma: no cover - direct script execution
    from cli import load_scenario, _write_scenario
    from planner import plan, validate_scenario

APP_ROOT = Path(__file__).resolve().parent.parent
MAX_BODY = 1024 * 1024
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/styles.css": "styles.css",
    "/app.js": "app.js",
    "/map.js": "map.js",
    "/planner.html": "planner.html",
}


def _reject_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


class AeroRouteHandler(BaseHTTPRequestHandler):
    server_version = "AeroRoute/1.0"

    def _send_json(self, status: int, value: Any) -> None:
        payload = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _read_json(self) -> Any:
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            # Requests from normal clients include Content-Length; rejecting an
            # unbounded stream keeps this intentionally local server bounded.
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_BODY:
            raise ValueError("request body is too large")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("incomplete request body")
        try:
            return json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("request body must be valid JSON") from exc

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlsplit(self.path).path)
        if path == "/api/health":
            self._send_json(200, {"ok": True})
            return
        if path == "/api/scenario":
            try:
                self._send_json(200, load_scenario())
            except Exception as exc:
                self._error(500, str(exc) or "stored scenario is invalid")
            return
        filename = STATIC_FILES.get(path)
        if filename is None:
            self._error(404, "not found")
            return
        target = (APP_ROOT / filename).resolve()
        try:
            if target.parent != APP_ROOT.resolve() or not target.is_file():
                self._error(404, "not found")
                return
            payload = target.read_bytes()
        except OSError:
            self._error(404, "not found")
            return
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlsplit(self.path).path)
        if path not in {"/api/plan", "/api/scenario"}:
            self._error(404, "not found")
            return
        try:
            value = self._read_json()
            scenario = validate_scenario(value)
            if path == "/api/plan":
                self._send_json(200, plan(scenario))
            else:
                _write_scenario(scenario)
                self._send_json(200, {"ok": True})
        except ValueError as exc:
            self._error(400, str(exc) or "bad request")
        except Exception as exc:
            self._error(500, str(exc) or "request failed")

    def log_message(self, format: str, *args: Any) -> None:
        # Keep command-line use quiet; errors are still returned to clients.
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local AeroRoute server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        server = ThreadingHTTPServer((args.host, args.port), AeroRouteHandler)
    except OSError as exc:
        parser.error(str(exc))
    print(f"AeroRoute server listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
