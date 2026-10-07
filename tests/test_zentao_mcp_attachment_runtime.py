"""Opt-in binary MCP acceptance using disposable HTTP fixtures and a local image."""

from email.parser import BytesParser
from email.policy import default
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from uuid import uuid4

from test_zentao_mcp_runtime import MetadataClient


@unittest.skipUnless(
    os.environ.get("MTX_TEST_ZENTAO_MCP_ATTACHMENTS") == "1",
    "Set MTX_TEST_ZENTAO_MCP_ATTACHMENTS=1 to run disposable attachment containers",
)
class AttachmentRuntimeTests(unittest.TestCase):
    def test_binary_transfer_and_lookup_through_real_mcp_container(self):
        content = b"large-binary-fixture\x00\xff" * 100_000
        checksum = hashlib.sha256(content).hexdigest()
        uploads = []
        credentials = []
        source_credentials = []

        class Fixture(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, data):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def do_GET(self):
                if self.path.startswith("/source"):
                    source_credentials.append((self.headers.get("token"), self.headers.get("Authorization")))
                    self.send_response(200)
                    self.end_headers()
                    if self.path.startswith("/source/slow"):
                        started = time.monotonic()
                        try:
                            for index in range(70):
                                time.sleep(max(0, index + 1 - (time.monotonic() - started)))
                                self.wfile.write(content[len(content) * index // 70:len(content) * (index + 1) // 70])
                                self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            pass  # The source deadline cancels this download before upload.
                    else:
                        self.wfile.write(content)
                    return
                credentials.append(self.headers.get("token"))
                if self.path.endswith("/download"):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(uploads[0]["file"])
                elif self.path.endswith("/files/101"):
                    self.reply({"result": "success", "file": {"id": "101", "title": "附件日志.txt",
                               "objectType": "bug", "objectID": "50", "size": len(content)}})
                else:
                    self.reply({"status": "success", "bug": {"id": "50", "deleted": "0"}})

            def do_POST(self):
                credentials.append(self.headers.get("token"))
                body = self.rfile.read(int(self.headers["Content-Length"]))
                document = BytesParser(policy=default).parsebytes(
                    b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
                fields = {}
                for part in document.iter_parts():
                    name = part.get_param("name", header="Content-Disposition")
                    fields[name] = part.get_payload(decode=True)
                    if name == "file":
                        fields["filename"] = part.get_filename()
                uploads.append(fields)
                self.reply({"result": "success", "status": "success", "data": {"id": "101"}})

        fixture = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        fixture.daemon_threads = True
        thread = threading.Thread(target=fixture.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(fixture.server_close)
        self.addCleanup(fixture.shutdown)
        source = f"http://127.0.0.1:{fixture.server_port}"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            mcp_port = listener.getsockname()[1]
        name = f"attachment-acceptance-{uuid4().hex[:12]}"
        image = os.environ.get("MTX_ATTACHMENT_MCP_IMAGE", "zentao-mcp:2026-10-04-attachments")
        with tempfile.TemporaryDirectory(prefix="attachment-runtime-") as directory:
            Path(directory).chmod(0o755)
            config = Path(directory) / "config.yaml"
            config.write_text(f'''port: "127.0.0.1:{mcp_port}"
enable_toon: false
telemetry:
  endpoint: ""
  insecure: true
servers:
  - name: zentao
    schema_url: /config/zentao-openapi.json
    base_url: "{source}/api.php/v2"
    instance_url: "{source}"
    attachment_source_origins: ["{source}"]
    attachment_max_bytes: 104857600
    allow:
      - methods: [GET, POST, PUT, DELETE]
        regex: ".*"
    block: []
''')
            try:
                subprocess.run(["docker", "run", "-d", "--pull", "never", "--name", name,
                                "--network", "host", "--mount", f"type=bind,src={directory},dst=/config/runtime,readonly",
                                image, "-config", "/config/runtime/config.yaml"],
                               check=True, capture_output=True, timeout=30)
                client = MetadataClient(mcp_port)
                deadline = time.monotonic() + 20
                while True:
                    try:
                        client.metadata()
                        break
                    except (OSError, ConnectionError):
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(0.2)
                tools = client.request("tools/list", {})["tools"]
                self.assertIn("upload_bug_attachment", {tool["name"] for tool in tools})
                args = {"bugId": 50, "filename": "附件日志.txt", "contentType": "text/plain",
                        "size": len(content), "sha256": checksum,
                        "downloadUrl": source + "/source?signature=disposable-secret"}
                result = client.request("tools/call", {"name": "upload_bug_attachment", "arguments": args})
                self.assertEqual(result["structuredContent"]["status"], "success")
                self.assertEqual(result["structuredContent"]["id"], 101)
                self.assertEqual(uploads[0]["file"], content)
                self.assertEqual(uploads[0]["filename"], "附件日志.txt")
                self.assertEqual(uploads[0]["objectType"], b"bug")
                self.assertEqual(uploads[0]["objectID"], b"50")
                verified = client.request("tools/call", {"name": "get_bug_attachment", "arguments": {"bugId": 50, "fileId": 101}})
                self.assertEqual(verified["structuredContent"]["sha256"], checksum)
                self.assertEqual(verified["structuredContent"]["filename"], "附件日志.txt")
                self.assertEqual(set(credentials), {"disposable-runtime-test-token"})
                self.assertEqual(source_credentials, [(None, None)])
                if os.environ.get("MTX_TEST_ZENTAO_MCP_SOURCE_DEADLINE") == "1":
                    slow_args = {**args, "downloadUrl": source + "/source/slow?signature=disposable-secret"}
                    started = time.monotonic()
                    result = client.request(
                        "tools/call", {"name": "upload_bug_attachment", "arguments": slow_args},
                        timeout=75,
                    )["structuredContent"]
                    self.assertNotEqual(result["status"], "success")
                    # Headers arrived, but the source deadline leaves an incomplete file.
                    self.assertEqual(result["errorCode"], "file_integrity_failed")
                    self.assertIs(result["uncertain"], False)
                    self.assertGreaterEqual(time.monotonic() - started, 55)
                    self.assertLess(time.monotonic() - started, 70)
                    self.assertEqual(len(uploads), 1, "Source timeout must not call POST /files")
                    self.assertEqual(source_credentials[-1], (None, None))
                logs = subprocess.check_output(["docker", "logs", name], stderr=subprocess.STDOUT)
                self.assertNotIn(b"disposable-secret", logs)
                self.assertNotIn(b"disposable-runtime-test-token", logs)
            finally:
                subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True, timeout=30)
