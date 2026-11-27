import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.agent.demo import run_demo
from tests.support.agent import FakeFactory


class RunDemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_demo_passes_message_session_and_config(self) -> None:
        root = self.enterContext(tempfile.TemporaryDirectory())
        config_path = str(Path(root) / "config.json")
        workspace = str(Path(root) / "workspace")
        factory = FakeFactory(["demo reply"])

        result = await run_demo(
            message="hello",
            session_key="demo:session",
            config_path=config_path,
            workspace=workspace,
            from_config=factory,
        )

        self.assertEqual(result, "demo reply")
        self.assertEqual(
            factory.bot.calls,
            [{"message": "hello", "session_key": "demo:session"}],
        )
        self.assertEqual(
            factory.last_kwargs,
            {
                "config_path": config_path,
                "workspace": workspace,
            },
        )


if __name__ == "__main__":
    unittest.main()
