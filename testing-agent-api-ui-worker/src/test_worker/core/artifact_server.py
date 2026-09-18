"""Expose locally generated UI artifacts through a small read-only HTTP server."""

from __future__ import annotations

import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote, unquote, urlsplit

from . import logger


def build_artifact_url(local_path: str, artifacts_root_dir: str, artifacts_base_url: str) -> str:
    """Convert a local artifact path into its public worker URL."""
    if not local_path or not artifacts_base_url:
        return local_path

    root = Path(artifacts_root_dir).resolve()
    path = Path(local_path).resolve()
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        logger.warn("artifact path is outside configured root", {
            "path": str(path),
            "root": str(root),
        })
        return local_path

    encoded_path = quote(relative_path.as_posix(), safe="/")
    return f"{artifacts_base_url.rstrip('/')}/{encoded_path}"


class _ArtifactRequestHandler(SimpleHTTPRequestHandler):
    """Serve screenshot files without exposing other worker artifacts."""

    def send_head(self) -> BinaryIO | None:
        request_path = unquote(urlsplit(self.path).path).lstrip("/")
        root = Path(self.directory).resolve()
        requested_file = (root / request_path).resolve()
        try:
            requested_file.relative_to(root)
        except ValueError:
            self.send_error(404, "Artifact not found")
            return None

        if requested_file.suffix.lower() != ".png" or not requested_file.is_file():
            self.send_error(404, "Artifact not found")
            return None

        return super().send_head()

    def list_directory(self, path: str | os.PathLike[str]) -> None:
        self.send_error(404, "Directory listing is disabled")
        return None

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        logger.info("artifact http request", {"message": format % args})


class ArtifactHttpServer:
    """Lifecycle wrapper around the worker's artifact HTTP server."""

    def __init__(self, artifacts_root_dir: str, bind_host: str, port: int) -> None:
        root = Path(artifacts_root_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        handler = functools.partial(_ArtifactRequestHandler, directory=str(root))
        self._server = ThreadingHTTPServer((bind_host, port), handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self._thread is not None:
            return
        thread = threading.Thread(
            target=self._server.serve_forever,
            name="artifact-http-server",
            daemon=True,
        )
        thread.start()
        self._thread = thread

    def stop(self) -> None:
        if self._thread is None:
            self._server.server_close()
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        self._thread = None
