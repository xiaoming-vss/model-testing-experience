"""Opt-in actual platform/RustFS reads through a controlled disconnecting proxy."""

import json
import os
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from testing_agent_ai_worker.platform.http_client import PlatformHttpClient


@contextmanager
def proxy():
    session_path = Path(os.environ["S3_LIVE_SESSION_FILE"])
    session = json.loads(session_path.read_text())
    proof = json.loads(session_path.with_name("ui-proof.json").read_text())
    stable = proof["screenshots"][0]
    assert session["name"].startswith("s3-p1-")
    token = session["token"]
    state = {"authorizations": 0, "reads": 0, "urls": {}, "always_break": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # HTTP paths and errors must not log signed URLs or credentials.

        def do_GET(self):
            if self.path == "/download":
                result = httpx.get(
                    "http://127.0.0.1:9000" + stable, headers={"Authorization": "Bearer " + token}
                )
                if result.status_code != 200:
                    self.send_error(result.status_code)
                    return
                ticket = result.json()["data"]
                state["authorizations"] += 1
                path = "/object/" + str(state["authorizations"])
                state["urls"][path] = ticket["url"]
                ticket["url"] = f"http://127.0.0.1:{self.server.server_port}" + path
                data = json.dumps(ticket).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path in state["urls"]:
                assert self.headers.get("X-Worker-Token") is None
                assert self.headers.get("Authorization") is None
                result = httpx.get(state["urls"][self.path])
                state["reads"] += 1
                self.send_response(result.status_code)
                self.send_header("Content-Length", str(len(result.content)))
                self.end_headers()
                data = result.content
                if state["reads"] == 1 or state["always_break"]:
                    data = data[: len(data) // 2]
                self.wfile.write(data)
                self.wfile.flush()
                self.close_connection = True
            else:
                self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            PlatformHttpClient(f"http://127.0.0.1:{server.server_port}", "private-test-worker"),
            state,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@unittest.skipUnless(
    os.getenv("AI_WORKER_STORAGE_LIVE") == "1",
    "Requires dedicated local acceptance session",
)
class SignedDownloadLiveTests(unittest.TestCase):
    def test_real_wire_interruption_renews_authorization_and_recovers(self):
        with proxy() as (client, state):
            data = client.get_signed_file_bytes("/download")
            self.assertGreater(len(data), 100)
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(state["authorizations"], 2)
            self.assertEqual(state["reads"], 2)

    def test_real_wire_interruption_stops_after_three_attempts(self):
        with proxy() as (client, state):
            state["always_break"] = True
            with self.assertRaisesRegex(ValueError, "transport failure"):
                client.get_signed_file_bytes("/download")
            self.assertEqual(state["authorizations"], 3)
            self.assertEqual(state["reads"], 3)
