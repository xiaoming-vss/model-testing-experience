import unittest
from unittest.mock import AsyncMock, patch

from testing_agent_ai_worker_pi.cli.pi_demo import main, run_cli_demo


class _Printer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, value: str) -> None:
        self.lines.append(value)


class PiDemoCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_cli_demo_forwards_arguments_and_prints_content(self) -> None:
        printer = _Printer()
        captured: dict[str, str | None] = {}

        async def fake_runner(
            *,
            message: str,
            session_key: str,
            config_path: str | None,
            workspace: str | None,
        ) -> str:
            captured.update(
                {
                    "message": message,
                    "session_key": session_key,
                    "config_path": config_path,
                    "workspace": workspace,
                }
            )
            return "demo reply"

        result = await run_cli_demo(
            message="hello",
            session_key="demo:session",
            config_path="D:/tmp/config.json",
            workspace="D:/tmp/workspace",
            runner=fake_runner,
            printer=printer,
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            captured,
            {
                "message": "hello",
                "session_key": "demo:session",
                "config_path": "D:/tmp/config.json",
                "workspace": "D:/tmp/workspace",
            },
        )
        self.assertEqual(printer.lines, ["demo reply"])


class PiDemoMainTests(unittest.TestCase):
    def test_cli_accepts_required_task_configuration(self) -> None:
        with (
            patch("sys.argv", ["pi_demo", "--config-path", "task.json", "--workspace", "work"]),
            patch(
                "testing_agent_ai_worker_pi.cli.pi_demo.run_cli_demo", new_callable=AsyncMock
            ) as run,
        ):
            run.return_value = 0
            self.assertEqual(main(), 0)
        run.assert_awaited_once_with(
            config_path="task.json",
            workspace="work",
            message="What time is it in Tokyo?",
            session_key="demo:pi",
        )


if __name__ == "__main__":
    unittest.main()
