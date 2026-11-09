import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.models.task import (
    ExistingTestCases,
    RepositoryBinding,
    RequirementInput,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks.code_risk_analysis.context import build_code_context
from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import (
    CodeWorkspace,
    RepoWorkspace,
)


def _binding() -> RepositoryBinding:
    return RepositoryBinding.model_validate(
        {
            "bindingId": "b-1",
            "repositoryId": "repo-1",
            "pathWithNamespace": "team/repo-one",
            "branch": "feature/login",
            "baselineBranch": "release/1.0",
            "baseCommit": "abc123",
            "headCommit": "def456",
        }
    )


def _workspace(root: Path) -> CodeWorkspace:
    code_root = root / "code"
    repo_path = code_root / "repos" / "team-repo-one-12345678"
    repo_path.mkdir(parents=True)
    return CodeWorkspace(
        run_root=root,
        code_root=code_root,
        repositories=[
            RepoWorkspace(
                binding=_binding(),
                path=repo_path,
                base_commit="abc123",
                head_commit="def456",
                changed_files=["src/login.py", "src/logout.py"],
                diff_files=[
                    {
                        "old_path": "src/login.py",
                        "new_path": "src/login.py",
                        "diff": "@@ -1 +1 @@\n-old\n+new\n",
                    },
                    {
                        "old_path": "src/logout.py",
                        "new_path": "src/logout.py",
                        "diff": "@@ -1 +1 @@\n-old2\n+new2\n",
                    },
                ],
                files_changed=2,
                additions=2,
                deletions=2,
            )
        ],
    )


def _existing_tests() -> ExistingTestCases:
    return ExistingTestCases.model_validate(
        {
            "functionCases": [
                {
                    "suiteId": "fs-1",
                    "suiteName": "登录功能",
                    "caseId": "fc-1",
                    "title": "登录成功",
                    "priority": "P1",
                    "steps": ["输入账号密码"],
                    "expectedResults": ["进入首页"],
                }
            ],
            "apiCases": [
                {
                    "collectionId": "ac-1",
                    "collectionName": "登录接口",
                    "caseId": "api-1",
                    "name": "登录返回 token",
                    "method": "POST",
                    "urlTemplate": "/api/login",
                    "assertRules": [{"name": "code=200"}],
                    "lastRun": {"status": "passed", "finishedAt": "2026-08-21T10:00:00+08:00"},
                }
            ],
            "uiCases": [
                {
                    "suiteId": "us-1",
                    "suiteName": "登录页面",
                    "caseId": "ui-1",
                    "name": "登录按钮可见",
                    "stepsJson": '[{"action":"click"}]',
                }
            ],
        }
    )


def _task(*, requirement: bool = True) -> Task:
    return Task(
        task_id="task-1",
        attempt_id="run-1",
        task_type="code_risk_analysis",
        project_id="project-1",
        requirement_input=(
            RequirementInput(requirement_id="req-1", document_content="需求理解正文")
            if requirement
            else None
        ),
        existing_tests=_existing_tests(),
        payload=TaskPayload(openapi_content=""),
    )


class BuildCodeContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = _workspace(self.root)

    def test_context_includes_requirement_manifest_diff_and_existing_tests(self) -> None:
        context = build_code_context(_task(), self.workspace, max_diff_chars=10_000)

        self.assertIn("需求理解正文", context.text)
        self.assertIn("read/grep/find/ls", context.text)
        self.assertIn("team/repo-one", context.text)
        self.assertIn("abc123", context.text)
        self.assertIn("def456", context.text)
        self.assertIn("src/login.py", context.text)
        self.assertIn("+new2", context.text)
        self.assertIn("登录成功", context.text)
        self.assertIn("功能用例暂无执行记录", context.text)
        self.assertIn("登录返回 token", context.text)
        self.assertIn("passed", context.text)
        self.assertIn("登录按钮可见", context.text)
        self.assertEqual([], context.truncated_files)
        self.assertGreater(context.diff_chars, 0)
        self.assertEqual(1, len(context.manifest["repositories"]))

    def test_missing_requirement_is_marked_in_context(self) -> None:
        context = build_code_context(_task(requirement=False), self.workspace, max_diff_chars=1000)

        self.assertIn("任务快照缺少需求理解记录", context.text)

    def test_diff_over_budget_truncates_whole_files_and_records_them(self) -> None:
        context = build_code_context(_task(), self.workspace, max_diff_chars=40)

        self.assertIn("+new", context.text)
        self.assertNotIn("+new2", context.text)
        self.assertEqual(["src/logout.py"], context.truncated_files)
        self.assertEqual(40, context.manifest["maxDiffChars"])
        self.assertEqual(["src/logout.py"], context.manifest["truncatedFiles"])

    def test_manifest_preserves_local_repository_paths(self) -> None:
        context = build_code_context(_task(), self.workspace, max_diff_chars=10_000)

        repository = json.loads(json.dumps(context.manifest))["repositories"][0]
        self.assertEqual("repos/team-repo-one-12345678", repository["localPath"])
        self.assertEqual(["src/login.py", "src/logout.py"], repository["changedFiles"])


if __name__ == "__main__":
    unittest.main()
