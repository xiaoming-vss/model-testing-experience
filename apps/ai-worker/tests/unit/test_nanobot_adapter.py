"""Nanobot adapter contract tests."""

import unittest
from types import SimpleNamespace

from testing_agent_ai_worker.agent.nanobot import NanobotAgent


class _FakeSdk:
    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *_exc):
        self.exited = True
        return False

    async def run(self, message, *, session_key, media=None):
        self.calls.append({"message": message, "session_key": session_key, "media": media})
        return self.result


class NanobotAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_normalizes_result_and_forwards_media(self) -> None:
        sdk = _FakeSdk(
            SimpleNamespace(
                content="answer",
                stop_reason=None,
                metadata={"finish_reason": "length"},
                usage=SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14),
            )
        )

        async with NanobotAgent(sdk) as agent:
            result = await agent.run("prompt", session_key="run-1", media=["image.png"])

        self.assertTrue(sdk.entered)
        self.assertTrue(sdk.exited)
        self.assertEqual(sdk.calls[0]["session_key"], "run-1")
        self.assertEqual(sdk.calls[0]["media"], ["image.png"])
        self.assertEqual(result.content, "answer")
        self.assertEqual(result.finish_reason, "length")
        self.assertEqual(result.usage["input_tokens"], 10.0)
        self.assertEqual(result.usage["total_tokens"], 14.0)

    async def test_run_prefers_stop_reason_and_tolerates_missing_usage(self) -> None:
        sdk = _FakeSdk(
            SimpleNamespace(
                content="answer",
                stop_reason="stop",
                metadata={"finish_reason": "length"},
                usage=None,
            )
        )

        async with NanobotAgent(sdk) as agent:
            result = await agent.run("prompt", session_key="run-2")

        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage, {})


if __name__ == "__main__":
    unittest.main()
