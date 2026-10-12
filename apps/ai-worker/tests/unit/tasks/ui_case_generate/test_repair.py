import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.tasks.ui_case_generate.executor import UiCaseNanobotExecutor
from tests.unit.tasks.ui_case_generate import test_executor as fixtures

VALID_YAML = fixtures.VALID_YAML


class UiRepairTests(unittest.TestCase):
    def execute(self, root, runner, progress, downloader=None):
        downloader = downloader or Mock(return_value=Path(root) / "source")
        executor = UiCaseNanobotExecutor(
            nanobot_config=NanobotConfig(runtime_root=root),
            source_downloader=SimpleNamespace(download_and_extract=downloader),
            skill_runner=runner,
        )
        return executor.execute(
            fixtures.UiCaseExecutorTests()._task(), datetime.now().astimezone(), progress.append
        )

    def test_repairs_yaml_then_keyword_error_and_preserves_source(self):
        runner = Mock(
            side_effect=[
                "[broken",
                VALID_YAML.replace("keyword: open", "keyword: nonexistent"),
                VALID_YAML,
            ]
        )
        progress, downloader = [], Mock()
        with tempfile.TemporaryDirectory() as root:
            downloader.return_value = Path(root) / "source"
            result = self.execute(root, runner, progress, downloader)
            self.assertEqual(len(list(Path(root).rglob("attempt-*.json"))), 3)
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(result.output_yaml, VALID_YAML)
        self.assertEqual(runner.call_count, 3)
        downloader.assert_called_once()
        first, *repairs = [call.kwargs for call in runner.call_args_list]
        self.assertTrue(all(call["input_text"].startswith(first["input_text"]) for call in repairs))
        self.assertEqual(
            [
                json.loads(p.result_summary_json)["outputValidation"]["repairAttempt"]
                for p in progress[1:]
            ],
            [1, 2],
        )
        self.assertTrue(
            all(p.intermediate_json_text == progress[0].intermediate_json_text for p in progress)
        )

    def test_exhaustion_does_not_publish_invalid_cases(self):
        runner = Mock(return_value="- name: incomplete")
        with tempfile.TemporaryDirectory() as root:
            result = self.execute(root, runner, [])
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("3 次", result.error_message)
        self.assertEqual(result.output_yaml, "")
        self.assertEqual(runner.call_count, 3)

    def test_download_and_model_failures_do_not_trigger_repair(self):
        with tempfile.TemporaryDirectory() as root:
            runner = Mock()
            result = self.execute(root, runner, [], Mock(side_effect=ValueError("download")))
            self.assertEqual(result.status, TaskStatus.FAILED)
            runner.assert_not_called()
            for failure in [RuntimeError("network"), SimpleNamespace(content="", error="auth")]:
                runner = (
                    Mock(side_effect=failure)
                    if isinstance(failure, Exception)
                    else Mock(return_value=failure)
                )
                with self.assertRaises(RuntimeError):
                    self.execute(root, runner, [])
                self.assertEqual(runner.call_count, 1)
            runner = Mock(return_value=SimpleNamespace(content=VALID_YAML, finish_reason="length"))
            result = self.execute(root, runner, [])
            self.assertEqual(result.status, TaskStatus.FAILED)
            self.assertEqual(runner.call_count, 1)
