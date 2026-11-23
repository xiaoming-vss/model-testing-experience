from __future__ import annotations

import asyncio
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testing_agent_perf_worker.compiler.compiler import compile_run_spec
from testing_agent_perf_worker.contracts.spec import load_run_spec
from testing_agent_perf_worker.core.config import Settings
from testing_agent_perf_worker.runner.k6 import K6Runner
from testing_agent_perf_worker.runner.workspace import Workspace


@pytest.mark.skipif(shutil.which("k6") is None, reason="k6 not installed")
async def test_real_k6_step_failure_priority(tmp_path: Path) -> None:
    class Endpoint(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(404 if self.path == "/missing" else 200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Endpoint)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        path = tmp_path / "spec.yaml"
        path.write_text(
            f"""specVersion: "1.0"
runId: step-priority
case:
  name: priority
  steps:
    - name: unexpected
      path: /missing
      onFailure: continue
      checks: [{{type: status, value: 200}}]
      extract: [{{name: missing, from: json, path: missing}}]
    - name: expected
      path: /missing
      expectedStatuses: [404]
      checks: [{{type: status, value: 404}}]
  load: {{model: vus, vus: 1, duration: "1s"}}
  acceptance: {{source: missing, confirmed: false}}
environment: {{baseUrl: "http://127.0.0.1:{port}", variables: {{}}}}
remoteWrite: {{url: "http://127.0.0.1:{port}/write", pushInterval: "1s"}}
""",
            encoding="utf-8",
        )
        settings = Settings()
        settings.k6.expected_version = ""
        workspace = Workspace.create(tmp_path / "runs", "step-priority")
        compiled = compile_run_spec(load_run_spec(path), tmp_path, workspace.root, settings)
        execution = await K6Runner(settings).run(compiled, workspace)
        assert execution.exit_code == 0
        assert execution.summary is not None
        metrics = execution.summary["metrics"]
        assert metrics["mtx_step_failures"]["values"]["count"] > 0
        assert (
            metrics["mtx_step_results"]["values"]["count"]
            == 2 * metrics["mtx_step_failures"]["values"]["count"]
        )
        assert metrics["checks"]["values"]["rate"] == 1
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(shutil.which("k6") is None, reason="k6 not installed")
async def test_real_k6_runs_fixed_template(tmp_path: Path) -> None:
    posts: list[bytes] = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    class Sink(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            posts.append(self.rfile.read(length))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
    sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    threads = [
        threading.Thread(target=target.serve_forever, daemon=True),
        threading.Thread(target=sink.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()

    try:
        target_port = target.server_address[1]
        sink_port = sink.server_address[1]
        spec_path = tmp_path / "case.yaml"
        spec_path.write_text(
            f"""
specVersion: "1.0"
runId: real-k6-001
case:
  name: real-k6
  steps:
    - name: ping
      method: GET
      path: /ping
      checks:
        - type: status
          op: eq
          value: 200
  load:
    model: vus
    vus: 1
    duration: "1s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
environment:
  baseUrl: "http://127.0.0.1:{target_port}"
  variables: {{}}
remoteWrite:
  url: "http://127.0.0.1:{sink_port}/api/v1/write"
  pushInterval: "1s"
limits:
  maxDurationSeconds: 30
  stopGraceSeconds: 5
""",
            encoding="utf-8",
        )

        settings = Settings()
        settings.k6.binary = "k6"
        settings.k6.expected_version = ""
        settings.runner.workspace_root = str(tmp_path / "runs")
        spec = load_run_spec(spec_path)
        workspace = Workspace.create(Path(settings.runner.workspace_root), spec.run_id)
        compiled = compile_run_spec(spec, tmp_path, workspace.root, settings)

        execution = await asyncio.wait_for(K6Runner(settings).run(compiled, workspace), timeout=30)

        assert execution.exit_code == 0
        assert execution.summary_missing is False
        assert execution.summary is not None
        assert execution.summary["metrics"]["http_reqs"]["values"]["count"] >= 1
        assert posts
    finally:
        target.shutdown()
        sink.shutdown()
        target.server_close()
        sink.server_close()
