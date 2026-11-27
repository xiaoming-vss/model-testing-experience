import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import testing_agent_ai_worker.cli.agent_chain_demo as chain_demo_module
from testing_agent_ai_worker.cli.agent_chain_demo import main, run_chain_demo
from testing_agent_ai_worker.tasks.api_case_generate.chain import ChainRunResult
from tests.support.cli import LinePrinter


class PiChainDemoCliTests(unittest.IsolatedAsyncioTestCase):
    def test_command_line_parses_input_and_options(self) -> None:
        argv = [
            "testing-agent-ai-chain-demo",
            "--source-json-path",
            "spec.json",
            "--session-key",
            "demo:cli",
            "--extra-instruction",
            "覆盖登录",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(
                chain_demo_module,
                "run_chain_demo",
                new_callable=AsyncMock,
                return_value=0,
            ) as runner,
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(runner.await_args.kwargs["source_json_path"], "spec.json")
        self.assertEqual(runner.await_args.kwargs["session_key"], "demo:cli")
        self.assertEqual(runner.await_args.kwargs["extra_instruction"], "覆盖登录")

    def test_command_line_requires_input_without_calling_model(self) -> None:
        with (
            patch.object(sys, "argv", ["testing-agent-ai-chain-demo"]),
            patch("sys.stderr"),
            patch.object(chain_demo_module, "run_chain_demo") as runner,
        ):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        runner.assert_not_called()

    async def test_run_chain_demo_reads_interface_file_and_prints_two_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "interfaces.json"
            source_path.write_text(
                '{"interfaces":[{"interfaceId":"interface-1"}]}', encoding="utf-8"
            )
            config_path = str(Path(temp_dir) / "config.json")
            workspace = str(Path(temp_dir) / "workspace")
            printer = LinePrinter()
            captured: dict[str, str | None] = {}

            async def fake_chain_runner(
                *,
                source_text: str,
                session_key: str,
                extractor_skill_name: str,
                generator_skill_name: str,
                config_path: str | None,
                workspace: str | None,
                extra_instruction: str,
            ) -> ChainRunResult:
                captured.update(
                    {
                        "source_text": source_text,
                        "session_key": session_key,
                        "extractor_skill_name": extractor_skill_name,
                        "generator_skill_name": generator_skill_name,
                        "config_path": config_path,
                        "workspace": workspace,
                        "extra_instruction": extra_instruction,
                    }
                )
                return ChainRunResult(
                    extractor_output="json result",
                    generator_output="yaml result",
                )

            exit_code = await run_chain_demo(
                source_json_path=str(source_path),
                session_key="demo:chain",
                extractor_skill_name="mtx-extract-interface-test-config",
                generator_skill_name="mtx-generate-api-test-case",
                config_path=config_path,
                workspace=workspace,
                extra_instruction="帮我生成登录、项目增删改查的用例",
                runner=fake_chain_runner,
                printer=printer,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            captured,
            {
                "source_text": '{"interfaces":[{"interfaceId":"interface-1"}]}',
                "session_key": "demo:chain",
                "extractor_skill_name": "mtx-extract-interface-test-config",
                "generator_skill_name": "mtx-generate-api-test-case",
                "config_path": config_path,
                "workspace": workspace,
                "extra_instruction": "帮我生成登录、项目增删改查的用例",
            },
        )
        self.assertEqual(
            printer.lines,
            [
                "=== extractor output ===",
                "json result",
                "=== yaml generator output ===",
                "yaml result",
            ],
        )

    def test_main_uses_explicit_path_and_returns_runner_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "interfaces.json"
            source_path.write_text(
                '{"interfaces":[{"interfaceId":"interface-1"}]}', encoding="utf-8"
            )
            original_runner = chain_demo_module.run_chain_demo
            captured: dict[str, str | None] = {}

            async def fake_run_chain_demo(**kwargs) -> int:
                captured.update(kwargs)
                return 0

            chain_demo_module.run_chain_demo = fake_run_chain_demo
            try:
                exit_code = main(
                    source_json_path=str(source_path),
                    session_key="demo:chain",
                    extractor_skill_name="mtx-extract-interface-test-config",
                    generator_skill_name="mtx-generate-api-test-case",
                )
            finally:
                chain_demo_module.run_chain_demo = original_runner

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["source_json_path"], str(source_path))
        self.assertEqual(captured["session_key"], "demo:chain")
        self.assertEqual(captured["extractor_skill_name"], "mtx-extract-interface-test-config")
        self.assertEqual(captured["generator_skill_name"], "mtx-generate-api-test-case")


if __name__ == "__main__":
    unittest.main()
