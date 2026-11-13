import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from testing_agent_ai_worker.agent.paths import resolve_task_workspace
from testing_agent_ai_worker.config.models import NanobotConfig, PiConfig
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import (
    GitlabCredentials,
    LlmCredentials,
    RepositoryBinding,
    RequirementInput,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks.repository_profile.executor import (
    READ_ONLY_TOOLS,
    RepositoryProfileExecutor,
)
from testing_agent_ai_worker.tasks.repository_profile.workspace import (
    ProfileRepoWorkspace,
    ProfileWorkspace,
)

VALID_PROFILE = {
    "repositories": [
        {
            "repositoryId": "repo-1",
            "pathWithNamespace": "team/repo-1",
            "role": "backend",
            "responsibilitySummary": "提供登录接口",
            "techStack": ["Java", "Spring Boot"],
            "keyPaths": ["src"],
            "confidence": 0.86,
            "evidence": ["pom.xml"],
        }
    ],
    "overallSummary": "当前需求主要涉及后端仓库",
}


def _task(*, task_type: str = "repository_profile") -> Task:
    return Task(
        task_id="task-1",
        attempt_id="run-1",
        generate_task_id="generate-1",
        task_type=task_type,
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="req-1",
        requirement_input=RequirementInput(
            requirementId="req-1",
            name="登录需求",
            documentType="richtext",
            documentContent="需求理解正文",
        ),
        bindings=[
            RepositoryBinding.model_validate(
                {
                    "bindingId": "binding-repo-1",
                    "repositoryId": "repo-1",
                    "instanceUrl": "https://gitlab.example.com",
                    "pathWithNamespace": "team/repo-1",
                    "cloneUrl": "https://gitlab.example.com/team/repo-1.git",
                    "branch": "feature/login",
                    "headCommit": "def456",
                    "connectionId": "conn-1",
                }
            )
        ],
        payload=TaskPayload(
            openapi_content="",
            llm_credentials=LlmCredentials(
                model="m",
                base_url="https://llm.example.com/v1",
                api_key="llm-key",
            ),
        ),
    )


class _FakeCredentialsFetcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def __call__(self, task: Task) -> list[GitlabCredentials]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("credential endpoint down")
        return [
            GitlabCredentials(
                connection_id="conn-1",
                base_url="https://gitlab.example.com",
                access_token="secret-token",
                repository_ids=["repo-1"],
            )
        ]


class _PromptRunner:
    def __init__(self, output: str | None = None, *, fail: bool = False) -> None:
        self.output = output if output is not None else json.dumps(VALID_PROFILE)
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        skill = Path(kwargs["workspace"]) / "skills/mtx-repository-profile-analysis/SKILL.md"
        if not skill.is_file():
            raise AssertionError("Pi workspace is missing the downloaded repository profile skill")
        if self.fail:
            raise RuntimeError("model failed")
        return self.output


class _RepairingPromptRunner:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]


class RepositoryProfileExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent_config = PiConfig(runtime_root=self.temp.name)
        workspace = resolve_task_workspace(self.agent_config, _task())
        skill = workspace / "skills/mtx-repository-profile-analysis/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Repository profile", encoding="utf-8")
        self.run_root = Path(self.temp.name) / "run"
        self.code_root = self.run_root / "code"
        repo_path = self.code_root / "repos" / "team-repo-1"
        repo_path.mkdir(parents=True)
        (repo_path / "src").mkdir()
        (repo_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        self.workspace = ProfileWorkspace(
            run_root=self.run_root,
            code_root=self.code_root,
            repositories=[
                ProfileRepoWorkspace(
                    binding=_task().bindings[0],
                    path=repo_path,
                    head_commit="def456",
                    order=0,
                    top_level_entries=["src/", "pom.xml"],
                )
            ],
            unavailable=[],
        )

    def _executor(self, runner: _PromptRunner, credentials: _FakeCredentialsFetcher | None = None):
        return RepositoryProfileExecutor(
            agent_config=self.agent_config,
            credentials_fetcher=credentials or _FakeCredentialsFetcher(),
            workspace_preparer=lambda *args, **kwargs: self.workspace,
            prompt_runner=runner,
        )

    def test_success_runs_read_only_prompt_and_returns_profile(self) -> None:
        runner = _PromptRunner()
        progress: list[tuple[str, str]] = []
        result = self._executor(runner).execute(
            _task(),
            datetime.now().astimezone(),
            lambda item: progress.append((item.current_stage, item.stage_status)),
        )

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(VALID_PROFILE, json.loads(result.output_yaml or ""))
        self.assertEqual(
            [("preparing_workspace", "running"), ("profiling", "running")],
            progress,
        )
        self.assertEqual(READ_ONLY_TOOLS, runner.calls[0]["tools"])
        self.assertEqual(str(self.code_root), runner.calls[0]["workspace"])
        self.assertIn("repositoryId", runner.calls[0]["input_text"])
        self.assertFalse(self.run_root.exists())

    def test_contract_failure_retains_workspace(self) -> None:
        result = self._executor(_PromptRunner('{"repositories": []}')).execute(
            _task(), datetime.now().astimezone(), lambda _item: None
        )

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("顶层字段", result.error_message or "")
        self.assertTrue((self.run_root / ".retain-until").exists())

    def test_contract_failure_is_repaired_at_most_twice(self) -> None:
        runner = _RepairingPromptRunner(
            [
                '{"repositories": [], "overallSummary": "无"}',
                json.dumps(VALID_PROFILE),
            ]
        )
        progress: list[tuple[str, str]] = []
        result = self._executor(runner).execute(
            _task(),
            datetime.now().astimezone(),
            lambda item: progress.append((item.current_stage, item.stage_status)),
        )

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(2, len(runner.calls))
        self.assertIn("校验问题", runner.calls[1]["input_text"])
        self.assertIn(("profiling", "repairing"), progress)

    def test_non_pi_backend_fails(self) -> None:
        executor = RepositoryProfileExecutor(
            agent_config=NanobotConfig(),
            credentials_fetcher=_FakeCredentialsFetcher(),
            workspace_preparer=lambda *args, **kwargs: self.workspace,
        )
        result = executor.execute(_task(), datetime.now().astimezone(), lambda _item: None)
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("Pi", result.error_message or "")

    def test_missing_understanding_fails(self) -> None:
        task = _task()
        task.requirement_input = None
        result = self._executor(_PromptRunner()).execute(
            task, datetime.now().astimezone(), lambda _item: None
        )
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("材料整理", result.error_message or "")

    def test_all_bindings_unavailable_fails_before_credentials(self) -> None:
        task = _task()
        task.bindings[0].profile_error = "无权限"
        task.bindings[0].clone_url = ""
        credentials = _FakeCredentialsFetcher()
        result = self._executor(_PromptRunner(), credentials).execute(
            task, datetime.now().astimezone(), lambda _item: None
        )
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("所有绑定仓库", result.error_message or "")
        self.assertEqual(0, credentials.calls)

    def test_credentials_failure_is_reported(self) -> None:
        result = self._executor(_PromptRunner(), _FakeCredentialsFetcher(fail=True)).execute(
            _task(), datetime.now().astimezone(), lambda _item: None
        )
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("GitLab 凭据不可用", result.error_message or "")

    def test_unexpected_model_failure_is_sanitized(self) -> None:
        result = self._executor(_PromptRunner(fail=True)).execute(
            _task(), datetime.now().astimezone(), lambda _item: None
        )
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertNotIn("model failed", result.error_message or "")
        self.assertTrue((self.run_root / ".retain-until").exists())

    def test_rejects_wrong_task_type(self) -> None:
        result = self._executor(_PromptRunner()).execute(
            _task(task_type="code_risk_analysis"),
            datetime.now().astimezone(),
            lambda _item: None,
        )
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("不支持的任务类型", result.error_message or "")


if __name__ == "__main__":
    unittest.main()
