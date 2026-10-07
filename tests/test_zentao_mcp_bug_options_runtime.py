"""Verify the published MCP with a schema overlay against an isolated upstream."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from test_zentao_mcp_runtime import MetadataClient

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/zentao-mcp/enable-bug-options.py"
spec = importlib.util.spec_from_file_location("bug_options_schema", SCRIPT)
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class BugOptionsSchemaTests(unittest.TestCase):
    def test_overlay_is_idempotent_and_preserves_existing_fields(self):
        operation = {"requestBody": {"content": {"application/json": {
            "schema": {"properties": {"title": {"type": "string"}}}}}}}
        schema = {"paths": {"/bugs": {"post": json.loads(json.dumps(operation))},
                            "/bugs/:bugID": {"put": json.loads(json.dumps(operation))},
                            "/executions/:executionID/builds": {"get": {}}}}
        result = patcher.patch_schema(schema)
        snapshot = json.dumps(result)
        self.assertEqual(json.dumps(patcher.patch_schema(result)), snapshot)
        props = result["paths"]["/bugs"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]
        self.assertEqual(props["title"], {"type": "string"})
        self.assertEqual(props["assignedTo"]["type"], "string")
        file = result["paths"]["/files/{fileID}"]["get"]
        self.assertEqual(file["parameters"][0]["name"], "fileID")
        self.assertTrue(file["parameters"][0]["required"])


@unittest.skipUnless(os.environ.get("MTX_TEST_ZENTAO_MCP_BUG_OPTIONS") == "1",
                     "Set MTX_TEST_ZENTAO_MCP_BUG_OPTIONS=1 for disposable MCP acceptance")
class BugOptionsRuntimeTests(unittest.TestCase):
    def test_version_paging_user_listing_and_assignment_reach_upstream(self):
        reads, writes, tokens = [], [], []

        class Fixture(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, data):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def do_GET(self):
                parsed = urlsplit(self.path)
                reads.append((parsed.path, parse_qs(parsed.query)))
                tokens.append(self.headers.get("token"))
                if parsed.path.endswith("/users"):
                    self.reply({"status": "success", "users": [{"id": "1", "account": "dev", "realname": "开发甲"}]})
                elif parsed.path.endswith("/files/101"):
                    self.reply({"status":"success", "file":{"id":"101", "objectType":"bug", "objectID":"50", "extension":"png"}})
                else:
                    self.reply({"status": "success", "builds": [{"id": "60", "name": "v1.0", "project": "10", "product": "40", "execution": "20"}]})

            def do_POST(self):
                tokens.append(self.headers.get("token"))
                writes.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.reply({"status": "success", "id": 50})

            def do_PUT(self):
                self.assert_path = self.path
                tokens.append(self.headers.get("token"))
                writes.append({"path": self.path, "payload": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
                self.reply({"status": "success"})

        fixture = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        threading.Thread(target=fixture.serve_forever, daemon=True).start()
        self.addCleanup(fixture.server_close)
        self.addCleanup(fixture.shutdown)
        source = f"http://127.0.0.1:{fixture.server_port}"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        image = os.environ.get("MTX_BUG_OPTIONS_MCP_IMAGE", "zentao-mcp:2026-10-04-attachments")
        name = "bug-options-acceptance-" + uuid4().hex[:12]
        with tempfile.TemporaryDirectory(prefix="mcp-bug-options-") as directory:
            root = Path(directory)
            root.chmod(0o755)
            raw = subprocess.check_output(["docker", "run", "--rm", "--pull", "never", "--entrypoint", "cat", image, "/config/zentao-openapi.json"])
            schema = root / "schema.json"
            schema.write_text(json.dumps(patcher.patch_schema(json.loads(raw))))
            config = root / "config.yaml"
            config.write_text(f'''port: "127.0.0.1:{port}"
enable_toon: false
telemetry:
  endpoint: ""
  insecure: true
servers:
  - name: zentao
    schema_url: /config/runtime/schema.json
    base_url: "{source}/api.php/v2"
    instance_url: "{source}"
    attachment_source_origins: ["{source}"]
    attachment_max_bytes: 104857600
    allow:
      - methods: [GET, POST, PUT]
        regex: ".*"
    block: []
''')
            try:
                subprocess.run(["docker", "run", "-d", "--pull", "never", "--name", name,
                                "--network", "host", "--mount", f"type=bind,src={root},dst=/config/runtime,readonly",
                                image, "-config", "/config/runtime/config.yaml"], check=True, capture_output=True)
                client = MetadataClient(port)
                deadline = time.monotonic() + 20
                while True:
                    try:
                        client.metadata()
                        break
                    except (OSError, ConnectionError):
                        if time.monotonic() >= deadline:
                            logs = subprocess.check_output(["docker", "logs", name], stderr=subprocess.STDOUT)
                            raise AssertionError(logs.decode())
                        time.sleep(0.2)
                for tool, args in (
                    ("get_executions_executionID_builds", {"executionID": 20, "pageID": 2, "recPerPage": 100}),
                    ("get_users", {"browseType": "inside", "pageID": 2, "recPerPage": 100}),
                    ("get_files_fileID", {"fileID": 101}),
                    ("post_bugs", {"payload": {"productID": 40, "title": "test", "openedBuild": ["60", "61"], "assignedTo": "dev"}}),
                    ("put_bugs_bugID", {"bugID": 50, "payload": {"openedBuild": ["61"], "assignedTo": "dev"}}),
                ):
                    result = client.request("tools/call", {"name": tool, "arguments": args})
                    self.assertFalse(result.get("isError"), result)
                self.assertEqual(reads[0], ("/api.php/v2/executions/20/builds", {"pageID": ["2"], "recPerPage": ["100"]}))
                self.assertEqual(reads[1], ("/api.php/v2/users", {"browseType": ["inside"], "pageID": ["2"], "recPerPage": ["100"]}))
                self.assertEqual(reads[2], ("/api.php/v2/files/101", {}))
                self.assertEqual(writes[0]["assignedTo"], "dev")
                self.assertEqual(writes[0]["openedBuild"], ["60", "61"])
                self.assertEqual(writes[1], {"path": "/api.php/v2/bugs/50", "payload": {"openedBuild": ["61"], "assignedTo": "dev"}})
                self.assertEqual(set(tokens), {"disposable-runtime-test-token"})
            finally:
                subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)
