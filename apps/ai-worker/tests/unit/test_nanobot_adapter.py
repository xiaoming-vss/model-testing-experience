"""Nanobot adapter contract tests."""

import unittest
from types import SimpleNamespace

from testing_agent_ai_worker.agent.nanobot import NanobotAgent
from testing_agent_ai_worker.core.errors import AgentOutputError


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
        # The SDK continues a token-limited answer itself; its agent-level outcome is
        # what decides completeness, not the stale raw provider reason in metadata.
        sdk = _FakeSdk(
            SimpleNamespace(
                content="answer",
                stop_reason="completed",
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
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage["input_tokens"], 10.0)
        self.assertEqual(result.usage["total_tokens"], 14.0)

    async def test_run_accepts_legacy_stop_reason_and_tolerates_missing_usage(self) -> None:
        sdk = _FakeSdk(
            SimpleNamespace(
                content="answer",
                stop_reason="stop",
                metadata={},
                usage=None,
            )
        )

        async with NanobotAgent(sdk) as agent:
            result = await agent.run("prompt", session_key="run-2")

        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage, {})

    async def test_incomplete_outcomes_raise_instead_of_returning_partial_text(self) -> None:
        # The SDK only logs these outcomes and hands back a placeholder or partial text.
        cases = [
            ("error", "模型调用出错，请检查模型服务或授权后重试"),
            ("max_iterations", "模型在限定轮次内没有完成生成，请缩小任务范围或简化指令后重试"),
            ("empty_final_response", "模型没有返回内容，请重试"),
            ("cancelled", "模型调用已取消"),
            ("something_new", "模型没有正常完成生成，请重试；持续出现时请检查模型服务配置"),
        ]
        for stop_reason, message in cases:
            with self.subTest(stop_reason=stop_reason):
                sdk = _FakeSdk(
                    SimpleNamespace(
                        content="partial or placeholder text",
                        stop_reason=stop_reason,
                        metadata={},
                        usage=None,
                    )
                )
                with self.assertRaises(AgentOutputError) as caught:
                    async with NanobotAgent(sdk) as agent:
                        await agent.run("prompt", session_key="run-3")
                self.assertEqual(str(caught.exception), message)

    async def test_raw_truncation_without_an_agent_outcome_is_reported(self) -> None:
        sdk = _FakeSdk(
            SimpleNamespace(
                content="cut off",
                stop_reason=None,
                metadata={"finish_reason": "length"},
                usage=None,
            )
        )
        with self.assertRaisesRegex(AgentOutputError, "截断"):
            async with NanobotAgent(sdk) as agent:
                await agent.run("prompt", session_key="run-4")


if __name__ == "__main__":
    unittest.main()
