"""Minimal HTTP health endpoint for Kubernetes probes."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

DEFAULT_HEALTH_HOST = "0.0.0.0"
DEFAULT_HEALTH_PORT = 8080
HEALTH_PATH = "/healthz"


class _HealthRequestHandler(BaseHTTPRequestHandler):
    """Serve a static health response; the process owns liveness semantics."""

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != HEALTH_PATH:
            self.send_error(404)
            return
        body = b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress per-request access logs from probe traffic."""


class HealthServer:
    """Run the health endpoint in a daemon thread."""

    def __init__(
        self,
        host: str = DEFAULT_HEALTH_HOST,
        port: int = DEFAULT_HEALTH_PORT,
    ) -> None:
        self._server = ThreadingHTTPServer((host, port), _HealthRequestHandler)
        self._server.daemon_threads = True
        self._thread = Thread(
            target=self._server.serve_forever,
            name="health-server",
            daemon=True,
        )
        self._started = False

    @property
    def port(self) -> int:
        """Return the bound port; useful when tests bind port 0."""
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            self._server.server_close()
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        self._started = False


def health_port_from_env() -> int | None:
    """Read the probe port; unset disables the server for local runs."""
    raw = os.getenv("TEST_WORKER_HEALTH_PORT", "")
    if not raw:
        return None
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_HEALTH_PORT
    return port if 0 <= port <= 65535 else DEFAULT_HEALTH_PORT
