"""Real Pi delegation against a local model, including failure and cleanup."""

import asyncio
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from testing_agent_ai_worker.agent.pi import _CHILDREN, Pi
from testing_agent_ai_worker.config.models import PiConfig


@unittest.skipUnless(os.environ.get("PI_RUNTIME_SMOKE") == "1", "Set PI_RUNTIME_SMOKE=1")
class PiSubagentSmoke(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(Path("/proc").exists(), "Requires Linux process information")
    async def test_cancellation_reaps_the_child_process_group(self):
        child_started = threading.Event()
        release = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if "【委派任务】" in str(data["messages"]):
                    child_started.set()
                    release.wait(15)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                delta = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "child",
                            "type": "function",
                            "function": {
                                "name": "subagent",
                                "arguments": json.dumps({"tasks": ["分析"]}),
                            },
                        }
                    ],
                }
                for change, reason in [(delta, None), ({}, "tool_calls")]:
                    event = {
                        "id": "chat",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [{"index": 0, "delta": change, "finish_reason": reason}],
                    }
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")

        def live_group(pgid):
            members = []
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                    if int(fields[2]) == pgid and fields[0] != "Z":
                        members.append(int(entry.name))
                except (OSError, ValueError, IndexError):
                    continue
            return members

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "work" / "skills").mkdir(parents=True)
                config = {
                    **PiConfig(
                        runtime_root=tmp, stream_idle_timeout_seconds=30, run_timeout_seconds=60
                    ).model_dump(),
                    "model": "test-model",
                    "api_key": "dummy-key",
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                }
                path = root / "config.json"
                path.write_text(json.dumps(config))
                bot = Pi.from_config(config_path=str(path), workspace=str(root / "work"))
                pending = asyncio.create_task(bot.run_with_subagents("材料", session_key="run"))
                try:
                    self.assertTrue(await asyncio.to_thread(child_started.wait, 15))
                    pgid = next(iter(_CHILDREN))
                    self.assertGreaterEqual(len(live_group(pgid)), 2)
                    pending.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await pending
                    for _ in range(30):
                        if not live_group(pgid):
                            break
                        await asyncio.sleep(0.1)
                    self.assertEqual(live_group(pgid), [])
                finally:
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join()

    async def test_delegation_and_child_failure(self):
        scenarios = (
            ("test_points", False, False),
            ("test_points", True, False),
            ("detailed_cases", False, False),
            ("detailed_cases", False, True),
            ("test_point_review", False, False),
        )
        for kind, fail, clarify in scenarios:
            with self.subTest(kind=kind, fail=fail, clarify=clarify):
                requests = []
                lock = threading.Lock()
                active = 0
                max_active = 0

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *_):
                        pass

                    def do_POST(self):
                        nonlocal active, max_active
                        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                        with lock:
                            requests.append(data)
                        messages = data["messages"]
                        is_child = any("【委派任务】" in str(m.get("content")) for m in messages)
                        is_result = any(m.get("role") == "tool" for m in messages)
                        if is_child:
                            with lock:
                                active += 1
                                max_active = max(max_active, active)
                            time.sleep(0.2)
                            with lock:
                                active -= 1
                        if is_child and fail:
                            self.send_response(500)
                            self.end_headers()
                            return
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.end_headers()
                        if is_child:
                            delta, reason = (
                                {
                                    "role": "assistant",
                                    "content": (
                                        "CLARIFICATION_REQUIRED: 缺少审批结果"
                                        if clarify
                                        else "子任务分析结果"
                                    ),
                                },
                                "stop",
                            )
                        elif is_result:
                            delta, reason = {"role": "assistant", "content": '{"ok":true}'}, "stop"
                        else:
                            delta = {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-child",
                                        "type": "function",
                                        "function": {
                                            "name": "subagent",
                                            "arguments": json.dumps(
                                                {
                                                    "tasks": ["分析登录流程"]
                                                    * (1 if fail or clarify else 3)
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                            reason = "tool_calls"
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
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp)
                        (root / "work" / "skills").mkdir(parents=True)
                        config = {
                            **PiConfig(
                                runtime_root=tmp,
                                stream_idle_timeout_seconds=30,
                                run_timeout_seconds=60,
                            ).model_dump(),
                            "model": "test-model",
                            "api_key": "dummy-key",
                            "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                        }
                        path = root / "config.json"
                        path.write_text(json.dumps(config))
                        bot = Pi.from_config(config_path=str(path), workspace=str(root / "work"))
                        if fail:
                            with self.assertRaisesRegex(RuntimeError, "子任务"):
                                await bot.run_with_subagents(
                                    "冻结材料 marker", session_key="run", delegation_kind=kind
                                )
                        else:
                            result = await bot.run_with_subagents(
                                "冻结材料 marker", session_key="run", delegation_kind=kind
                            )
                            if clarify:
                                self.assertEqual(
                                    result.content, "CLARIFICATION_REQUIRED: 缺少审批结果"
                                )
                                self.assertGreaterEqual(len(requests), 2)
                                continue
                            self.assertEqual(json.loads(result.content), {"ok": True})
                            self.assertEqual(len(requests), 5)
                            self.assertEqual(max_active, 2)
                            children = [
                                item for item in requests if "【委派任务】" in str(item["messages"])
                            ]
                            self.assertEqual(len(children), 3)
                            child = children[0]
                            self.assertIn("冻结材料 marker", str(child["messages"]))
                            self.assertIn("分析登录流程", str(child["messages"]))
                            if kind == "detailed_cases":
                                self.assertIn(
                                    "skills/mtx-generate-solution-test-cases/references/subagent.md",
                                    str(child["messages"]),
                                )
                                self.assertIn("生成子 Agent", str(child["messages"]))
                            elif kind == "test_point_review":
                                self.assertIn(
                                    "skills/mtx-generate-traceable-test-points/references/subagent.md",
                                    str(child["messages"]),
                                )
                                self.assertIn("复核子 Agent", str(child["messages"]))
                            else:
                                self.assertIn(
                                    "skills/mtx-generate-traceable-test-points/references/subagent.md",
                                    str(child["messages"]),
                                )
                                self.assertIn("生成子 Agent", str(child["messages"]))
                            names = [t["function"]["name"] for t in child.get("tools", [])]
                            self.assertNotIn("subagent", names)
                            self.assertNotIn("bash", names)
                            self.assertIn("子任务分析结果", str(requests[-1]["messages"]))
                            self.assertIn("subagent_input", result.usage)
                        self.assertFalse(list(root.glob("pi-agent-*")))
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
