"""Explicit isolated container acceptance; never connects to configured platform services."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@unittest.skipUnless(
    os.environ.get("MTX_TEST_INTEGRATION_WORKER_RUNTIME") == "1",
    "Set MTX_TEST_INTEGRATION_WORKER_RUNTIME=1 for disposable Worker container acceptance",
)
class IntegrationWorkerRuntimeTests(unittest.TestCase):
    def test_two_containers_have_independent_identity_outbox_health_and_clean_stop(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, self.headers.get("X-Worker-Token"), body))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"job":null}')

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        containers = []
        try:
            with tempfile.TemporaryDirectory(prefix="mtx-integration-container-") as directory:
                config = Path(directory) / "worker.toml"
                config.write_text(
                    '[control_plane]\nbase_url="http://127.0.0.1:' + str(server.server_port) + '"\n'
                    'worker_token="disposable-worker-container-key"\n'
                    '[worker]\npoll_interval_seconds=0.1\n'
                    'health_file="/app/runtime/health.json"\n'
                    'evidence_file="/app/runtime/evidence.json"\n'
                )
                config.chmod(0o644)  # Same mode as manage.py's container configuration.
                image = os.environ.get("MTX_TEST_INTEGRATION_WORKER_IMAGE", "mtx/integration-worker:split-validation")
                for _ in range(2):
                    container = subprocess.check_output([
                        "docker", "run", "-d", "--network", "host",
                        "--mount", f"type=bind,source={config},target=/app/config/local.toml,readonly",
                        "--mount", "type=volume,target=/app/runtime", image,
                    ], text=True).strip()
                    containers.append(container)
                deadline = time.monotonic() + 15
                while len({body["workerId"] for _, _, body in requests}) < 2:
                    if time.monotonic() > deadline:
                        self.fail("Both isolated containers must reach the fake control-plane")
                    time.sleep(0.05)
                volumes = []
                for container in containers:
                    inspected = json.loads(subprocess.check_output(
                        ["docker", "inspect", container], text=True,
                    ))[0]
                    self.assertFalse(inspected["Config"].get("ExposedPorts"))
                    volumes.append(next(m["Name"] for m in inspected["Mounts"] if m["Destination"] == "/app/runtime"))
                    self.assertEqual(subprocess.check_output(
                        ["docker", "exec", container, "id", "-u"], text=True,
                    ).strip(), "10001")
                    subprocess.check_call(["docker", "exec", container, "mtx-integration-worker", "--healthcheck"])
                    subprocess.check_call([
                        "docker", "exec", container, "python", "-c",
                        "import importlib.util; assert all(importlib.util.find_spec(m) is None "
                        "for m in ['testing_agent', 'sqlalchemy', 'fastapi', 'boto3'])",
                    ])
                self.assertEqual(len(set(volumes)), 2)
                self.assertTrue(all(path == "/internal/integration-worker/jobs/claim" for path, _, _ in requests))
                self.assertTrue(all(token == "disposable-worker-container-key" for _, token, _ in requests))
                self.assertTrue(all(body["protocolVersions"] == [1] for _, _, body in requests))
                for container in containers:
                    subprocess.check_call(["docker", "stop", "-t", "15", container], stdout=subprocess.DEVNULL)
                    inspected = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
                    self.assertEqual(inspected["State"]["ExitCode"], 0)
        finally:
            for container in containers:
                subprocess.run(["docker", "rm", "-fv", container], capture_output=True, check=False)
            server.shutdown()
            server.server_close()
            thread.join()
