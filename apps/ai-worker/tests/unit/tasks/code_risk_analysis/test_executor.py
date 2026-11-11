import tempfile
import unittest
from datetime import datetime
from typing import Any

import yaml

from testing_agent_ai_worker.config.models import (
    CodeRiskAnalysisConfig,
    NanobotConfig,
    PiConfig,
)
from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import (
    ExistingTestCases,
    GitlabCredentials,
    LlmCredentials,
    RepositoryBinding,
    RequirementInput,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks.code_risk_analysis.context import ContextPackage
from testing_agent_ai_worker.tasks.code_risk_analysis.executor import (
    READ_ONLY_TOOLS,
    CodeRiskAnalysisExecutor,
)
from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import (
    CodeWorkspace,
    CodeWorkspaceError,
    RepoWorkspace,
    code_run_root,
)


def _task(
    *,
    requirement: RequirementInput | None = None,
    bindings: list[RepositoryBinding] | None = None,
    existing_tests: ExistingTestCases | None = None,
) -> Task:
    if requirement is None:
        requirement = RequirementInput.model_validate(
            {
                "requirementId": "req-1",
                "name": "登录功能需求",
                "documentType": "text",
                "documentContent": "需求理解记录正文",
            }
        )
    return Task(
        task_id="task-1",
        attempt_id="run-1",
        generate_task_id="generate-1",
        task_type="code_risk_analysis",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="req-1",
        requirement_input=requirement,
        bindings=bindings
        or [
            RepositoryBinding.model_validate(
                {
                    "bindingId": "b-1",
                    "repositoryId": "repo-1",
                    "instanceUrl": "https://gitlab.example.com",
                    "pathWithNamespace": "team/repo-one",
                    "cloneUrl": "https://gitlab.example.com/team/repo-one.git",
                    "branch": "feat/login",
                    "baselineBranch": "release/1.0",
                    "baseCommit": "abc123",
                    "headCommit": "def456",
                    "connectionId": "conn-1",
                }
            )
        ],
        existing_tests=existing_tests or ExistingTestCases(),
        gitlab_credentials_url="/internal/ai-worker/tasks/task-1/gitlab-credentials",
        payload=TaskPayload(
            openapi_content="",
            extra_instruction="",
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
            raise RuntimeError("凭证接口不可用")
        return [
            GitlabCredentials(
                connection_id="conn-1",
                base_url="https://gitlab.example.com",
                access_token="secret-token-1",
                repository_ids=["repo-1"],
            )
        ]


class _RecordingPromptRunner:
    def __init__(self, output: Any = None) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.output is not None:
            return self.output
        return (
            "changeOverview:\n"
            "  summary: 鉴权变更\n"
            "risks:\n"
            "  - level: high\n"
            "    reason: 鉴权逻辑变更\n"
            "    location: src/login.py\n"
            "    impact: 可能影响登录\n"
            "    evidence: [src/login.py]\n"
            "affectedCases: []\n"
            "coverageGaps:\n"
            "  - gap: 缺少失败路径\n"
            "    suggestion: 增加失败用例\n"
        )


class _AsyncPromptRunner:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._result()

    async def _result(self):
        return self.output


class _RepairingPromptRunner:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]


class CodeRiskAnalysisExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent_config = PiConfig(runtime_root=self.temp.name)
        self.task = _task()
        self.run_root = code_run_root(self.agent_config, self.task)
        self.workspace = self._workspace()

    def _workspace(self) -> CodeWorkspace:
        code_root = self.run_root / "code"
        repo_path = code_root / "repos" / "team-repo-one-12345678"
        repo_path.mkdir(parents=True)
        (repo_path / "src").mkdir()
        (repo_path / "src" / "login.py").write_text("def login(): pass", encoding="utf-8")
        (self.run_root / ".active").write_text("1", encoding="utf-8")
        binding = self.task.bindings[0]
        repo = RepoWorkspace(
            binding=binding,
            path=repo_path,
            base_commit="abc123",
            head_commit="def456",
            changed_files=["src/login.py"],
            diff_files=[
                {
                    "old_path": "src/login.py",
                    "new_path": "src/login.py",
                    "diff": "@@ -1 +1 @@\n-old\n+new\n",
                }
            ],
            files_changed=1,
            additions=1,
            deletions=1,
        )
        return CodeWorkspace(run_root=self.run_root, code_root=code_root, repositories=[repo])

    def _context(self) -> ContextPackage:
        return ContextPackage(
            text="# 需求理解记录\n\n需求理解记录正文",
            manifest={"repositories": self.workspace.manifest["repositories"]},
            diff_chars=20,
            truncated_files=["src/big.py"],
        )

    def _executor(
        self,
        *,
        prompt_runner=None,
        fetcher: _FakeCredentialsFetcher | None = None,
        workspace_preparer=None,
        context_builder=None,
        credentials_fetcher=None,
    ) -> CodeRiskAnalysisExecutor:
        return CodeRiskAnalysisExecutor(
            agent_config=self.agent_config,
            code_risk_config=CodeRiskAnalysisConfig(max_diff_chars=100),
            credentials_fetcher=credentials_fetcher or fetcher or _FakeCredentialsFetcher(),
            workspace_preparer=workspace_preparer
            or (lambda task, credentials, **kwargs: self.workspace),
            context_builder=context_builder or (lambda task, workspace, **kwargs: self._context()),
            prompt_runner=prompt_runner or _RecordingPromptRunner(),
        )

    def test_execute_success_builds_workspace_prompt_and_receipt(self) -> None:
        runner = _RecordingPromptRunner()
        executor = self._executor(prompt_runner=runner)
        progresses = []

        result = executor.execute(self.task, datetime.now().astimezone(), progresses.append)

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertIn("fetching_diff", [p.current_stage for p in progresses])
        call = runner.calls[0]
        self.assertEqual(READ_ONLY_TOOLS, call["tools"])
        self.assertEqual(str(self.workspace.code_root), call["workspace"])
        self.assertIn("需求理解记录正文", call["input_text"])
        self.assertNotIn("secret-token-1", call["input_text"])
        data = yaml.safe_load(result.output_yaml)
        self.assertEqual("def456", data["repositories"][0]["headCommit"])
        self.assertEqual("high", data["risks"][0]["level"])
        self.assertIn('"repositoryCount": 1', result.result_summary_json)
        self.assertFalse(self.run_root.exists())

    def test_execute_accepts_awaitable_prompt_result(self) -> None:
        runner = _AsyncPromptRunner(
            "changeOverview: {}\nrisks: []\naffectedCases: []\ncoverageGaps: []\n"
        )
        executor = self._executor(prompt_runner=runner)

        result = executor.execute(self.task, datetime.now().astimezone(), lambda _p: None)

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(1, len(runner.calls))

    def test_execute_repairs_invalid_report_at_most_twice(self) -> None:
        runner = _RepairingPromptRunner(
            [
                "changeOverview: {}\nrisks: []\naffectedCases:\n  - caseId: bad\n    impact: bad\ncoverageGaps: []\n",
                "changeOverview: {}\nrisks: []\naffectedCases: []\ncoverageGaps: []\n",
            ]
        )
        executor = self._executor(prompt_runner=runner)

        result = executor.execute(self.task, datetime.now().astimezone(), lambda _p: None)

        self.assertEqual(TaskStatus.SUCCESS, result.status)
        self.assertEqual(2, len(runner.calls))
        self.assertIn("校验问题", runner.calls[1]["input_text"])

    def test_execute_requires_requirement_understanding(self) -> None:
        runner = _RecordingPromptRunner()
        executor = self._executor(prompt_runner=runner)
        task = _task()
        task.requirement_input = None
        progresses = []

        result = executor.execute(task, datetime.now().astimezone(), progresses.append)

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("尚未完成需求分析", result.error_message or "")
        self.assertEqual([], progresses)
        self.assertEqual([], runner.calls)

    def test_execute_rejects_non_pi_backend(self) -> None:
        executor = CodeRiskAnalysisExecutor(
            agent_config=NanobotConfig(),
            credentials_fetcher=_FakeCredentialsFetcher(),
        )

        result = executor.execute(self.task, datetime.now().astimezone(), lambda _p: None)

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("仅支持 Pi", result.error_message or "")

    def test_execute_fails_when_credentials_unavailable(self) -> None:
        runner = _RecordingPromptRunner()
        executor = self._executor(prompt_runner=runner, fetcher=_FakeCredentialsFetcher(fail=True))
        progresses = []

        result = executor.execute(self.task, datetime.now().astimezone(), progresses.append)

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("凭证接口不可用", result.error_message or "")
        self.assertEqual([], progresses)
        self.assertEqual([], runner.calls)

    def test_execute_reports_workspace_errors(self) -> None:
        def fail_prepare(*_args, **_kwargs):
            raise CodeWorkspaceError("仓库 repo-1 无法获取 commit abc123")

        runner = _RecordingPromptRunner()
        executor = self._executor(prompt_runner=runner, workspace_preparer=fail_prepare)
        progresses = []

        result = executor.execute(self.task, datetime.now().astimezone(), progresses.append)

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("repo-1", result.error_message or "")
        self.assertEqual(["fetching_diff"], [p.current_stage for p in progresses])
        self.assertEqual([], runner.calls)

    def test_execute_rejects_incomplete_receipt_and_retains_workspace(self) -> None:
        runner = _RecordingPromptRunner(
            output=(
                "changeOverview: {}\n"
                "risks:\n"
                "  - level: high\n"
                "    reason: bad\n"
                "    location: src/login.py\n"
                "    impact: bad\n"
                "    evidence: [src/login.py]\n"
                "affectedCases:\n"
                "  - caseId: unknown\n"
                "    impact: bad\n"
                "coverageGaps: []\n"
            )
        )
        executor = self._executor(prompt_runner=runner)

        result = executor.execute(self.task, datetime.now().astimezone(), lambda _p: None)

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertIn("unknown_case_id", result.error_message or "")
        self.assertTrue(self.run_root.exists())
        self.assertTrue((self.run_root / ".retain-until").is_file())
        self.assertFalse((self.run_root / ".active").exists())

    def test_execute_hides_unexpected_exception_details(self) -> None:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret-token-1 should not leak")

        executor = self._executor(workspace_preparer=explode)

        result = executor.execute(self.task, datetime.now().astimezone(), lambda _p: None)

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertNotIn("secret-token-1", result.error_message or "")
        self.assertEqual("代码上下文准备或模型调用失败", result.error_message)


if __name__ == "__main__":
    unittest.main()
