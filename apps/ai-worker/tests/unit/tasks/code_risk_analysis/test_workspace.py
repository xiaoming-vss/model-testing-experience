import json
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from testing_agent_ai_worker.config.models import CodeRiskAnalysisConfig, PiConfig
from testing_agent_ai_worker.models.task import (
    ExistingTestCases,
    GitlabCredentials,
    RepositoryBinding,
    RequirementInput,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks import git_workspace as git_workspace_module
from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import (
    CodeWorkspaceError,
    cleanup_code_workspace,
    prepare_code_workspace,
    retain_failed_workspace,
    sweep_expired_workspaces,
)

DIFF_TEXT = """\
diff --git a/src/login.py b/src/login.py
index 111..222 100644
--- a/src/login.py
+++ b/src/login.py
@@ -1,2 +1,2 @@
-old
+new
 context
diff --git a/package-lock.json b/package-lock.json
new file mode 100644
--- /dev/null
+++ b/package-lock.json
@@ -0,0 +1 @@
+{}
"""


def _binding(**overrides) -> RepositoryBinding:
    data = {
        "bindingId": "b-1",
        "repositoryId": "repo-1",
        "instanceUrl": "https://gitlab.example.com",
        "pathWithNamespace": "team/repo-one",
        "cloneUrl": "https://gitlab.example.com/team/repo-one.git",
        "branch": "feature/login",
        "baselineBranch": "release/1.0",
        "baseCommit": "base-sha",
        "headCommit": "head-sha",
        "connectionId": "conn-1",
    }
    data.update(overrides)
    return RepositoryBinding.model_validate(data)


def _task(bindings=None) -> Task:
    return Task(
        task_id="task-1",
        attempt_id="run-1",
        task_type="code_risk_analysis",
        project_id="project-1",
        requirement_input=RequirementInput(requirement_id="req-1", document_content="需求理解正文"),
        bindings=bindings or [_binding()],
        existing_tests=ExistingTestCases(),
        payload=TaskPayload(openapi_content=""),
    )


def _credentials(token: str = "secret-token-1") -> list[GitlabCredentials]:
    return [
        GitlabCredentials(
            connection_id="conn-1",
            base_url="https://gitlab.example.com",
            access_token=token,
            repository_ids=["repo-1"],
        )
    ]


class _FakeGitRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, args, *, cwd=None, env=None, timeout=300.0):
        self.calls.append(
            {"args": list(args), "cwd": cwd, "env": dict(env or {}), "timeout": timeout}
        )
        if args[0] == "rev-parse":
            return "head-sha\n"
        if "diff" in args:
            return DIFF_TEXT
        return ""

    def all_args(self) -> str:
        return "\n".join(" ".join(call["args"]) for call in self.calls)


class CodeWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent_config = PiConfig(runtime_root=self.temp.name)
        self.config = CodeRiskAnalysisConfig(git_timeout_seconds=15, max_repos=5)
        self.task = _task()

    def test_prepare_clones_pinned_commits_and_builds_filtered_diff(self) -> None:
        runner = _FakeGitRunner()

        workspace = prepare_code_workspace(
            self.task,
            _credentials(),
            agent_config=self.agent_config,
            config=self.config,
            runner=runner,
        )

        clone = runner.calls[0]
        self.assertEqual("clone", clone["args"][0])
        self.assertIn("--filter=blob:none", clone["args"])
        self.assertIn("https://oauth2@gitlab.example.com/team/repo-one.git", clone["args"])
        self.assertNotIn("secret-token-1", runner.all_args())
        self.assertEqual("secret-token-1", clone["env"]["GIT_PASSWORD"])
        self.assertEqual("0", clone["env"]["GIT_TERMINAL_PROMPT"])
        diff_call = next(call for call in runner.calls if "diff" in call["args"])
        self.assertIn("core.quotePath=false", diff_call["args"])
        self.assertEqual(15.0, clone["timeout"])

        self.assertEqual("head-sha", workspace.repositories[0].head_commit)
        self.assertEqual(
            ["src/login.py", "package-lock.json"], workspace.repositories[0].changed_files
        )
        self.assertEqual(
            ["src/login.py"],
            [item["new_path"] for item in workspace.repositories[0].diff_files],
        )
        self.assertEqual(2, workspace.repositories[0].files_changed)
        self.assertEqual(2, workspace.repositories[0].additions)
        self.assertEqual(1, workspace.repositories[0].deletions)

        manifest = json.loads((workspace.code_root / "manifest.json").read_text("utf-8"))
        self.assertEqual("team/repo-one", manifest["repositories"][0]["pathWithNamespace"])
        self.assertEqual("base-sha", manifest["repositories"][0]["baseCommit"])
        self.assertEqual("head-sha", manifest["repositories"][0]["headCommit"])
        self.assertTrue(manifest["repositories"][0]["localPath"].startswith("repos/"))
        self.assertTrue((workspace.run_root / ".active").is_file())
        self.assertEqual([], list(workspace.run_root.glob(".git-auth-*")))

    def test_prepare_checks_out_head_and_verifies_it(self) -> None:
        runner = _FakeGitRunner()

        prepare_code_workspace(
            self.task,
            _credentials(),
            agent_config=self.agent_config,
            config=self.config,
            runner=runner,
        )

        checkout = next(call for call in runner.calls if call["args"][0] == "checkout")
        self.assertEqual(["checkout", "--detach", "head-sha"], checkout["args"])

    def test_prepare_rejects_head_mismatch(self) -> None:
        class MismatchRunner(_FakeGitRunner):
            def run(self, args, *, cwd=None, env=None, timeout=300.0):
                if args[0] == "rev-parse":
                    return "other-sha\n"
                return super().run(args, cwd=cwd, env=env, timeout=timeout)

        with self.assertRaisesRegex(CodeWorkspaceError, "HEAD .* 不一致"):
            prepare_code_workspace(
                self.task,
                _credentials(),
                agent_config=self.agent_config,
                config=self.config,
                runner=MismatchRunner(),
            )

    def test_prepare_requires_matching_credentials(self) -> None:
        with self.assertRaisesRegex(CodeWorkspaceError, "未匹配到 GitLab 凭据"):
            prepare_code_workspace(
                self.task,
                [],
                agent_config=self.agent_config,
                config=self.config,
                runner=_FakeGitRunner(),
            )

    def test_prepare_rejects_non_http_clone_url(self) -> None:
        with self.assertRaisesRegex(CodeWorkspaceError, "HTTP\\(S\\)"):
            prepare_code_workspace(
                _task([_binding(instanceUrl="", cloneUrl="file:///tmp/repo")]),
                _credentials(),
                agent_config=self.agent_config,
                config=self.config,
                runner=_FakeGitRunner(),
            )

    def test_prepare_rejects_clone_url_from_another_instance(self) -> None:
        with self.assertRaisesRegex(CodeWorkspaceError, "实例不一致"):
            prepare_code_workspace(
                _task([_binding(cloneUrl="https://other.example/team/repo-one.git")]),
                _credentials(),
                agent_config=self.agent_config,
                config=self.config,
                runner=_FakeGitRunner(),
            )

    def test_prepare_rejects_missing_pinned_commits_or_clone_url(self) -> None:
        for binding, message in (
            (_binding(cloneUrl=""), "缺少克隆地址"),
            (_binding(baseCommit=""), "缺少固定的 base/head commit"),
            (_binding(headCommit=""), "缺少固定的 base/head commit"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(CodeWorkspaceError, message):
                    prepare_code_workspace(
                        _task([binding]),
                        _credentials(),
                        agent_config=self.agent_config,
                        config=self.config,
                        runner=_FakeGitRunner(),
                    )

    def test_prepare_rejects_repository_count_over_limit(self) -> None:
        task = _task([_binding(), _binding(bindingId="b-2", repositoryId="repo-2")])
        with self.assertRaisesRegex(CodeWorkspaceError, "仓库数量超过上限"):
            prepare_code_workspace(
                task,
                _credentials(),
                agent_config=self.agent_config,
                config=CodeRiskAnalysisConfig(max_repos=1),
                runner=_FakeGitRunner(),
            )

    def test_cleanup_deletes_success_and_retains_failure(self) -> None:
        runner = _FakeGitRunner()
        workspace = prepare_code_workspace(
            self.task,
            _credentials(),
            agent_config=self.agent_config,
            config=self.config,
            runner=runner,
        )

        cleanup_code_workspace(workspace, success=False, config=self.config)
        self.assertTrue(workspace.run_root.is_dir())
        marker = workspace.run_root / ".retain-until"
        self.assertGreater(
            datetime.fromisoformat(marker.read_text("utf-8")),
            datetime.now(UTC),
        )
        self.assertFalse((workspace.run_root / ".active").exists())

        cleanup_code_workspace(workspace, success=True, config=self.config)
        self.assertFalse(workspace.run_root.exists())

    def test_retain_failed_workspace_is_noop_without_directory(self) -> None:
        missing = Path(self.temp.name) / "missing"
        retain_failed_workspace(missing, 24)
        self.assertFalse(missing.exists())

    def test_sweep_removes_only_expired_retained_workspaces(self) -> None:
        runs = Path(self.temp.name) / "workspaces" / "project-x" / "task-y" / "runs"
        expired = runs / "run-expired"
        active = runs / "run-active"
        naive = runs / "run-naive"
        for path, retain_until in (
            (expired, datetime.now(UTC) - timedelta(hours=1)),
            (active, datetime.now(UTC) + timedelta(hours=1)),
        ):
            path.mkdir(parents=True)
            (path / ".retain-until").write_text(retain_until.isoformat(), encoding="utf-8")
        # 手工写入的无时区时间按 UTC 解析,不因比较异常阻断整轮清扫。
        naive.mkdir(parents=True)
        (naive / ".retain-until").write_text(
            (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None).isoformat(),
            encoding="utf-8",
        )

        sweep_expired_workspaces(self.agent_config, now=datetime.now(UTC))

        self.assertFalse(expired.exists())
        self.assertFalse(naive.exists())
        self.assertTrue(active.exists())

    def test_real_git_clone_checkout_and_diff(self) -> None:
        repo = Path(self.temp.name) / "source"
        repo.mkdir()
        self._git(repo, "init", "-q", "-b", "main")
        self._git(repo, "config", "user.email", "tester@example.com")
        self._git(repo, "config", "user.name", "Tester")
        (repo / "login.py").write_text("old\n", encoding="utf-8")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-qm", "base")
        base = self._git(repo, "rev-parse", "HEAD").strip()
        self._git(repo, "checkout", "-qb", "feature/login")
        (repo / "login.py").write_text("new\n", encoding="utf-8")
        (repo / "package-lock.json").write_text("{}\n", encoding="utf-8")
        (repo / "需求.md").write_text("需求说明\n", encoding="utf-8")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-qm", "feature")
        head = self._git(repo, "rev-parse", "HEAD").strip()

        binding = _binding(
            instanceUrl="",
            cloneUrl=str(repo),
            baseCommit=base,
            headCommit=head,
            branch="feature/login",
            baselineBranch="main",
        )
        with patch.object(
            git_workspace_module, "authenticated_clone_url", side_effect=lambda url: url
        ):
            workspace = prepare_code_workspace(
                _task([binding]),
                _credentials(),
                agent_config=self.agent_config,
                config=self.config,
            )

        repo_workspace = workspace.repositories[0]
        self.assertEqual(head, repo_workspace.head_commit)
        self.assertEqual(
            {"login.py", "package-lock.json", "需求.md"},
            set(repo_workspace.changed_files),
        )
        self.assertEqual(
            {"login.py", "需求.md"},
            {item["new_path"] for item in repo_workspace.diff_files},
        )
        diffs = {item["new_path"]: item["diff"] for item in repo_workspace.diff_files}
        self.assertIn("+new", diffs["login.py"])
        self.assertIn("+需求说明", diffs["需求.md"])
        self.assertEqual(
            head,
            self._git(repo_workspace.path, "rev-parse", "HEAD").strip(),
        )
        self.assertEqual([], list(workspace.run_root.glob(".git-auth-*")))

    def test_task_run_root_rejects_dot_only_attempt_id(self) -> None:
        task = _task()
        task.attempt_id = ".."
        with tempfile.TemporaryDirectory() as temp:
            run_root = git_workspace_module.task_run_root(PiConfig(runtime_root=temp), task)
        task_root = run_root.parent.parent
        self.assertEqual("attempt", run_root.name)
        self.assertNotEqual(task_root, run_root)
        self.assertTrue(run_root.is_relative_to(task_root))

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        ).stdout


if __name__ == "__main__":
    unittest.main()
