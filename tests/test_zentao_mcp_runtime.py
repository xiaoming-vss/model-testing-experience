"""Opt-in runtime acceptance; default discovery never starts MCP containers."""

from http.client import RemoteDisconnected
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from test_zentao_mcp_deployment import (
    compose_command,
    compose_environment,
    prepare_deployment,
)

RUNTIME_ENABLED = os.environ.get("MTX_TEST_ZENTAO_MCP_RUNTIME") == "1"


class MetadataClient:
    def __init__(self, port):
        self.endpoint = f"http://127.0.0.1:{port}/zentao/mcp"
        self.opener = build_opener(ProxyHandler({}))
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "token": "disposable-runtime-test-token",
        }
        self.request_id = 0

    def request(self, method, params, notification=False, *, timeout=3):
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = self.request_id
        request = Request(
            self.endpoint, json.dumps(payload).encode(), self.headers, method="POST"
        )
        with self.opener.open(request, timeout=timeout) as response:
            if response.headers.get("Mcp-Session-Id"):
                self.headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
            body = response.read().decode()
            if notification:
                return {}
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                messages = [
                    json.loads(line[5:].strip())
                    for line in body.splitlines()
                    if line.startswith("data:")
                ]
                result = next(
                    item for item in messages if item.get("id") == payload["id"]
                )
            else:
                result = json.loads(body)
            if "error" in result:
                raise AssertionError(f"Metadata RPC failed: {result['error']}")
            return result["result"]

    def metadata(self):
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "mtx-runtime-acceptance", "version": "1"},
            },
        )
        self.headers["MCP-Protocol-Version"] = result["protocolVersion"]
        self.request("notifications/initialized", {}, notification=True)
        result = self.request(
            "tools/call", {"name": "get_zentao_instance", "arguments": {}}
        )
        if result.get("isError"):
            raise AssertionError("Instance metadata tool failed")
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        return json.loads(
            next(item["text"] for item in result["content"] if item["type"] == "text")
        )


@unittest.skipUnless(
    RUNTIME_ENABLED,
    "Set MTX_TEST_ZENTAO_MCP_RUNTIME=1 for explicit container acceptance",
)
class ZentaoMcpRuntimeTests(unittest.TestCase):
    def run_compose(self, name, *args):
        return subprocess.run(
            compose_command(self.deployments[name], *args),
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=compose_environment(),
        )

    def wait_metadata(self, port):
        deadline = time.monotonic() + 20
        while True:
            try:
                return MetadataClient(port).metadata()
            except (URLError, ConnectionError, TimeoutError, RemoteDisconnected):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)

    def test_two_containers_are_independent_and_restart_reads_edited_config(self):
        with tempfile.TemporaryDirectory(prefix="mtx-mcp-runtime-") as directory:
            self.root = Path(directory)
            suffix = uuid4().hex[:12]
            names = [f"acceptance-{suffix}-a", f"acceptance-{suffix}-b"]
            sockets = [socket.socket() for _ in names]
            try:
                for connection in sockets:
                    connection.bind(("127.0.0.1", 0))
                ports = [connection.getsockname()[1] for connection in sockets]
            finally:
                for connection in sockets:
                    connection.close()
            instances = {
                name: {
                    # No reachable upstream or real credential is used.
                    "api_base_url": f"http://127.0.0.1:1/{name}/api.php/v2",
                    "instance_url": f"https://{name}.example.test/zentao",
                    "host_port": port,
                }
                for name, port in zip(names, ports)
            }
            self.deployments = {
                name: prepare_deployment(self.root / name, name, port)
                for name, port in zip(names, ports)
            }

            def write_config(name):
                path = self.deployments[name] / "config/config.yaml"
                example = (self.deployments[name] / "config.example.yaml").read_text()
                content = example.replace(
                    "https://zentao.example.test/api.php/v2",
                    instances[name]["api_base_url"],
                ).replace(
                    "https://zentao.example.test", instances[name]["instance_url"]
                )
                temporary = path.with_suffix(".tmp")
                temporary.write_text(content)
                temporary.replace(path)

            attempted = []
            try:
                for name in names:
                    write_config(name)
                    self.run_compose(name, "pull")
                    attempted.append(name)
                    self.run_compose(
                        name,
                        "up",
                        "-d",
                        "--no-build",
                        "--pull",
                        "never",
                        "--wait",
                        "--wait-timeout",
                        "25",
                    )
                for name, port in zip(names, ports):
                    metadata = self.wait_metadata(port)
                    self.assertEqual(metadata["schemaVersion"], 1)
                    self.assertEqual(
                        metadata["instanceUrl"], instances[name]["instance_url"]
                    )
                    self.assertEqual(
                        metadata["apiBaseUrl"], instances[name]["api_base_url"]
                    )
                first, second = names
                previous_instance = instances[first]["instance_url"]
                instances[first]["instance_url"] = (
                    "https://changed.example.test/zentao/subpath"
                )
                instances[first]["api_base_url"] = (
                    "http://127.0.0.1:1/changed/api.php/v2"
                )
                write_config(first)
                self.assertEqual(
                    self.wait_metadata(ports[0])["instanceUrl"], previous_instance
                )
                self.run_compose(first, "restart")
                changed = self.wait_metadata(ports[0])
                self.assertEqual(
                    changed["instanceUrl"], instances[first]["instance_url"]
                )
                self.assertEqual(
                    changed["apiBaseUrl"], instances[first]["api_base_url"]
                )
                self.run_compose(first, "stop")
                self.assertEqual(
                    self.wait_metadata(ports[1])["instanceUrl"],
                    instances[second]["instance_url"],
                )
                with self.assertRaises(URLError):
                    MetadataClient(ports[0]).metadata()
            finally:
                cleanup_errors = []
                for name in reversed(attempted):
                    try:
                        self.run_compose(name, "down", "--remove-orphans")
                    except subprocess.SubprocessError as error:
                        cleanup_errors.append(error)
                if cleanup_errors:
                    raise RuntimeError(
                        f"Could not remove temporary deployments: {attempted}"
                    ) from cleanup_errors[0]
