import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from testing_agent_ai_worker.config.models import PiConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.tasks.ui_case_generate.executor import UiCaseExecutor
from testing_agent_ai_worker.tasks.ui_case_generate.repository_source import RepositorySource
from tests.unit.tasks.ui_case_generate import test_executor as fixtures

VALID_YAML = fixtures.VALID_YAML


class _Preparer:
    def __init__(self, root, *, error: Exception | None = None) -> None:
        self.root = Path(root)
        self.error = error
        self.calls = 0

    def prepare(self, *, task, credentials) -> RepositorySource:
        self.calls += 1
        if self.error is not None:
            raise self.error
        source_root = self.root / "source"
        source_root.mkdir(exist_ok=True)
        return RepositorySource(
            binding=task.bindings[0],
            run_root=self.root / "run",
            source_root=source_root,
            commit="a1b2c3d",
        )


class UiRepairTests(unittest.TestCase):
    def execute(self, root, runner, progress, preparer=None):
        preparer = preparer or _Preparer(root)
        executor = UiCaseExecutor(
            agent_config=PiConfig(runtime_root=root),
            repository_source_preparer=preparer,
            credentials_fetcher=lambda task: ["credential"],
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
        progress = []
        with tempfile.TemporaryDirectory() as root:
            preparer = _Preparer(root)
            result = self.execute(root, runner, progress, preparer)
            self.assertEqual(len(list(Path(root).rglob("attempt-*.json"))), 3)
        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertEqual(result.output_yaml, VALID_YAML)
        self.assertEqual(runner.call_count, 3)
        self.assertEqual(preparer.calls, 1)
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

    def test_source_and_model_failures_do_not_trigger_repair(self):
        with tempfile.TemporaryDirectory() as root:
            runner = Mock()
            result = self.execute(root, runner, [], _Preparer(root, error=ValueError("repository")))
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
