import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from testing_agent_ai_worker.config.models import PiConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import (
    GitlabCredentials,
    RepositoryBinding,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks.git_workspace import task_run_root
from testing_agent_ai_worker.tasks.ui_case_generate.executor import UiCaseExecutor
from testing_agent_ai_worker.tasks.ui_case_generate.repository_source import (
    RepositorySource,
    RepositorySourceError,
)
from tests.unit.tasks.ui_case_generate.test_executor import VALID_YAML

COMMIT = "a" * 40
TOKEN = "secret-token-1"
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/ui_generation"


def _binding() -> RepositoryBinding:
    return RepositoryBinding.model_validate(
        {
            "bindingId": "binding-1",
            "repositoryId": "repo-1",
            "instanceUrl": "https://gitlab.example.com",
            "pathWithNamespace": "team/web-admin",
            "cloneUrl": "https://gitlab.example.com/team/web-admin.git",
            "branch": "main",
            "headCommit": COMMIT,
            "connectionId": "conn-1",
        }
    )


def _task(*, metadata: dict | None = None, three_stage: bool = False) -> Task:
    payload_metadata = {
        "sourceKind": "repository",
        "sourceRepository": {
            "bindingId": "binding-1",
            "repositoryId": "repo-1",
            "pathWithNamespace": "team/web-admin",
            "branch": "main",
            "commit": COMMIT,
            "commitMode": "profile",
        },
        "sourceCommit": COMMIT,
    }
    if three_stage:
        payload_metadata.update(
            {
                "uiWorkflowVersion": "ui_three_stage/1.0",
                "functionalCases": json.loads((FIXTURES / "cases.json").read_text()),
            }
        )
    payload_metadata.update(metadata or {})
    task = Task(
        task_id="ui-task-1",
        attempt_id="run-1",
        generate_task_id="generate-1",
        task_type="ui_case_generate",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        bindings=[_binding()],
        payload=TaskPayload(openapi_content="", metadata=payload_metadata),
    )
    return task


def _credentials(token: str = TOKEN) -> list[GitlabCredentials]:
    return [
        GitlabCredentials(
            connection_id="conn-1",
            base_url="https://gitlab.example.com",
            access_token=token,
            repository_ids=["repo-1"],
        )
    ]


class _RecordingPreparer:
    def __init__(self, run_root: Path, *, error: str = "") -> None:
        self.run_root = run_root
        self.error = error
        self.calls: list[dict] = []

    def prepare(self, *, task: Task, credentials) -> RepositorySource:
        self.calls.append({"task": task, "credentials": credentials})
        self.run_root.mkdir(parents=True, exist_ok=True)
        if self.error:
            raise RepositorySourceError(self.error)
        source_root = self.run_root / "source"
        source_root.mkdir(parents=True, exist_ok=True)
        (source_root / "page.vue").write_text("<div>登录</div>", encoding="utf-8")
        return RepositorySource(
            binding=task.bindings[0],
            run_root=self.run_root,
            source_root=source_root,
            commit=COMMIT,
        )


class UiCaseSourceDispatchTests(unittest.TestCase):
    def test_repository_source_uses_preparer_and_reports_identity(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            agent_config = PiConfig(runtime_root=root)
            task = _task()
            run_root = task_run_root(agent_config, task)
            preparer = _RecordingPreparer(run_root)
            fetcher = Mock(return_value=_credentials())
            progress = []
            executor = UiCaseExecutor(
                agent_config=agent_config,
                repository_source_preparer=preparer,
                credentials_fetcher=fetcher,
                skill_runner=lambda **kwargs: VALID_YAML,
            )

            result = executor.execute(task, datetime.now().astimezone(), progress.append)

            self.assertEqual(TaskStatus.SUCCESS, result.status)
            fetcher.assert_called_once_with(task)
            self.assertEqual(TOKEN, preparer.calls[0]["credentials"][0].access_token)
            self.assertFalse(run_root.exists())

        intermediate = json.loads(result.intermediate_json_text)
        self.assertEqual("repo-1", intermediate["sourceRepository"]["repositoryId"])
        self.assertEqual(COMMIT, intermediate["sourceRepository"]["commit"])
        self.assertEqual(COMMIT, intermediate["sourceCommit"])
        self.assertNotIn(TOKEN, result.intermediate_json_text)

        self.assertEqual(1, len(progress))
        progress_payload = json.loads(progress[0].intermediate_json_text)
        self.assertEqual("repo-1", progress_payload["sourceRepository"]["repositoryId"])
        self.assertEqual(COMMIT, progress_payload["sourceCommit"])
        self.assertNotIn(TOKEN, progress[0].intermediate_json_text)

    def test_repository_source_failure_retains_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            agent_config = PiConfig(runtime_root=root)
            task = _task()
            run_root = task_run_root(agent_config, task)
            executor = UiCaseExecutor(
                agent_config=agent_config,
                repository_source_preparer=_RecordingPreparer(run_root, error="仓库 clone 失败"),
                credentials_fetcher=Mock(return_value=_credentials()),
                skill_runner=lambda **kwargs: VALID_YAML,
            )

            result = executor.execute(task, datetime.now().astimezone(), lambda _: None)

            self.assertEqual(TaskStatus.FAILED, result.status)
            self.assertIn("仓库 clone 失败", result.error_message or "")
            self.assertTrue(run_root.is_dir())
            self.assertTrue((run_root / ".retain-until").is_file())
            self.assertFalse((run_root / ".active").exists())

    def test_repository_source_without_credentials_fails_before_clone(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            task = _task()
            preparer = Mock()
            executor = UiCaseExecutor(
                agent_config=PiConfig(runtime_root=root),
                repository_source_preparer=preparer,
                credentials_fetcher=Mock(return_value=[]),
                skill_runner=lambda **kwargs: VALID_YAML,
            )

            result = executor.execute(task, datetime.now().astimezone(), lambda _: None)

            self.assertEqual(TaskStatus.FAILED, result.status)
            self.assertIn("GitLab 凭据不可用", result.error_message or "")
            preparer.prepare.assert_not_called()

    def test_three_stage_repository_surface_reports_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            agent_config = PiConfig(runtime_root=root)
            task = _task(three_stage=True)
            task.checkpoint_enabled = True
            task.current_stage = "ui_surface"
            task.config_json = "{}"
            run_root = task_run_root(agent_config, task)
            surface = json.loads((FIXTURES / "surface.json").read_text())
            progress = []
            executor = UiCaseExecutor(
                agent_config=agent_config,
                repository_source_preparer=_RecordingPreparer(run_root),
                credentials_fetcher=Mock(return_value=_credentials()),
                skill_runner=lambda **kwargs: json.dumps(surface, ensure_ascii=False),
            )

            result = executor.execute(task, datetime.now().astimezone(), progress.append)

            self.assertIsNone(result)
            self.assertFalse(run_root.exists())

        self.assertEqual("waiting_review", progress[-1].stage_status)
        intermediate = json.loads(progress[-1].intermediate_json_text)
        self.assertEqual("repo-1", intermediate["sourceRepository"]["repositoryId"])
        self.assertEqual(COMMIT, intermediate["sourceCommit"])
        self.assertEqual(surface, intermediate["uiSurface"])
        self.assertNotIn(TOKEN, progress[-1].intermediate_json_text)


if __name__ == "__main__":
    unittest.main()
