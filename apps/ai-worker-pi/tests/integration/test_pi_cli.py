"""Opt-in real Pi CLI smoke against a local OpenAI streaming server; no paid calls."""

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from testing_agent_ai_worker_pi.config.models import PiConfig
from testing_agent_ai_worker_pi.pi_runtime.client import Pi, check_runtime


@unittest.skipUnless(
    os.environ.get("PI_RUNTIME_SMOKE") == "1", "Set PI_RUNTIME_SMOKE=1 for real Pi CLI"
)
class PiCliSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_real_cli_tool_execution_and_session_resume(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(data)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if len(requests) == 1:
                    delta = {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-test",
                                "type": "function",
                                "function": {
                                    "name": "write",
                                    "arguments": json.dumps(
                                        {"path": "proof.txt", "content": "Pi tool executed"}
                                    ),
                                },
                            }
                        ],
                    }
                    reason = "tool_calls"
                else:
                    delta = {"role": "assistant", "content": '{"ok":true}'}
                    reason = "stop"
                for change, finish in [(delta, None), ({}, reason)]:
                    event = {
                        "id": "chat-test",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [{"index": 0, "delta": change, "finish_reason": finish}],
                    }
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        check_runtime("pi")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                **PiConfig(runtime_root=tmp, stream_idle_timeout_seconds=20).model_dump(),
                "model": "test-model",
                "api_key": "dummy-key",
                "base_url": f"http://127.0.0.1:{server.server_port}/v1",
            }
            path = root / "config.json"
            path.write_text(json.dumps(config))
            work = root / "work"
            async with Pi.from_config(config_path=str(path), workspace=str(work)) as bot:
                result = await bot.run("Write a proof file.", session_key="persistent")
            self.assertEqual(json.loads(result.content), {"ok": True})
            self.assertEqual((work / "proof.txt").read_text(), "Pi tool executed")
            async with Pi.from_config(config_path=str(path), workspace=str(work)) as bot:
                result = await bot.run("Continue the same session.", session_key="persistent")
            self.assertEqual(result.finish_reason, "stop")
            self.assertEqual(len(requests), 3)
            history = json.dumps(requests[-1]["messages"])
            self.assertIn("Write a proof file.", history)
            self.assertIn("Continue the same session.", history)
            self.assertFalse(list(root.glob("pi-agent-*")))
