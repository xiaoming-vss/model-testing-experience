import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from testing_agent_ai_worker.config.loader import load_settings
from testing_agent_ai_worker.config.models import PiConfig, Settings, UiGenerationConfig
from testing_agent_ai_worker.models.task import (
    GitlabCredentials,
    RepositoryBinding,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks import git_workspace as git_workspace_module
from testing_agent_ai_worker.tasks.git_workspace import GitWorkspaceError
from testing_agent_ai_worker.tasks.ui_case_generate.repository_source import (
    RepositorySourceError,
    build_credentials_fetcher,
    cleanup_repository_source,
    prepare_repository_source,
)

COMMIT = "a" * 40
TOKEN = "secret-token-1"


def _binding(**overrides) -> RepositoryBinding:
    data = {
        "bindingId": "binding-1",
        "repositoryId": "repo-1",
        "instanceUrl": "https://gitlab.example.com",
        "pathWithNamespace": "team/web-admin",
        "cloneUrl": "https://gitlab.example.com/team/web-admin.git",
        "branch": "main",
        "headCommit": COMMIT,
        "connectionId": "conn-1",
    }
    data.update(overrides)
    return RepositoryBinding.model_validate(data)


def _task(
    *,
    binding: RepositoryBinding | None = None,
    metadata: dict | None = None,
    bindings: list[RepositoryBinding] | None = None,
    gitlab_credentials_url: str = "/internal/ai-worker/tasks/task-1/gitlab-credentials",
) -> Task:
    payload_metadata = {
        "sourceKind": "repository",
        "sourceRepository": {
            "bindingId": "binding-1",
            "repositoryId": "repo-1",
            "instanceUrl": "https://gitlab.example.com",
            "pathWithNamespace": "team/web-admin",
            "branch": "main",
            "commit": COMMIT,
            "commitMode": "profile",
        },
        "sourceCommit": COMMIT,
    }
    payload_metadata.update(metadata or {})
    return Task(
        task_id="task-1",
        attempt_id="run-1",
        generate_task_id="generate-1",
        task_type="ui_case_generate",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        bindings=bindings if bindings is not None else [binding or _binding()],
        gitlab_credentials_url=gitlab_credentials_url,
        payload=TaskPayload(openapi_content="", metadata=payload_metadata),
    )


def _credentials(token: str = TOKEN) -> list[GitlabCredentials]:
    return [
        GitlabCredentials(
            connection_id="conn-1",
            base_url="https://gitlab.example.com",
            access_token=token,
            repository_ids=["repo-1"],
        )
    ]


class _FakeGitRunner:
    def __init__(self, *, head: str = COMMIT, files: dict[str, str] | None = None) -> None:
        self.calls: list[dict] = []
        self.head = head
        self.files = files or {"src/App.tsx": "export const App = () => null\n"}
        self.available_commits: set[str] = set()

    def run(self, args, *, cwd=None, env=None, timeout=300.0):
        self.calls.append(
            {"args": list(args), "cwd": cwd, "env": dict(env or {}), "timeout": timeout}
        )
        if args[0] == "clone":
            repo = Path(args[-1])
            (repo / ".git" / "objects").mkdir(parents=True, exist_ok=True)
            for name, content in self.files.items():
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            return ""
        if args[0] == "cat-file":
            commit = args[-1].removesuffix("^{commit}")
            if commit in self.available_commits:
                return ""
            raise GitWorkspaceError("missing commit")
        if args[0] == "fetch" and args[-1] not in {"origin"} and not args[-1].startswith("+"):
            self.available_commits.add(args[-1])
            return ""
        if args[0] == "rev-parse":
            return f"{self.head}\n"
        return ""

    def all_args(self) -> str:
        return "\n".join(" ".join(call["args"]) for call in self.calls)


class RepositorySourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent_config = PiConfig(runtime_root=self.temp.name)
        self.config = UiGenerationConfig()

    def _prepare(self, task: Task, *, runner=None, credentials=None, config=None):
        return prepare_repository_source(
            task,
            _credentials() if credentials is None else credentials,
            agent_config=self.agent_config,
            config=config or self.config,
            runner=runner or _FakeGitRunner(),
        )

    def test_clones_whole_repository_fetches_branch_and_pinned_commit(self) -> None:
        runner = _FakeGitRunner()
        source = self._prepare(_task(), runner=runner)

        self.assertEqual(COMMIT, source.commit)
        self.assertEqual(source.run_root / "source", source.source_root)
        self.assertTrue((source.source_root / "src" / "App.tsx").is_file())
        self.assertFalse((source.source_root / ".git").exists())

        clone = next(call for call in runner.calls if call["args"][0] == "clone")
        self.assertIn("--filter=blob:none", clone["args"])
        self.assertIn("--no-checkout", clone["args"])
        self.assertFalse(any("sparse" in arg for arg in runner.all_args().split()))
        self.assertIn("https://oauth2@gitlab.example.com/team/web-admin.git", clone["args"])
        self.assertNotIn(TOKEN, runner.all_args())
        self.assertEqual(TOKEN, clone["env"]["GIT_PASSWORD"])
        self.assertEqual("0", clone["env"]["GIT_TERMINAL_PROMPT"])
        self.assertTrue(clone["env"]["GIT_ASKPASS"].endswith("askpass.sh"))

        fetch_calls = [call["args"] for call in runner.calls if call["args"][0] == "fetch"]
        self.assertTrue(
            any(any(arg.startswith("+refs/heads/main:") for arg in args) for args in fetch_calls)
        )
        self.assertTrue(any(args[-1] == COMMIT for args in fetch_calls))

        checkout = next(call for call in runner.calls if call["args"][0] == "checkout")
        self.assertEqual(["checkout", "--detach", COMMIT], checkout["args"])
        self.assertEqual([], list(source.run_root.glob(".git-auth-*")))

    def test_metadata_reports_repository_identity_without_credentials(self) -> None:
        source = self._prepare(_task())
        metadata = json.dumps(source.metadata, ensure_ascii=False)

        self.assertEqual("repository", source.metadata["sourceKind"])
        self.assertEqual(COMMIT, source.metadata["sourceCommit"])
        self.assertEqual("repo-1", source.metadata["sourceRepository"]["repositoryId"])
        self.assertEqual("team/web-admin", source.metadata["sourceRepository"]["pathWithNamespace"])
        self.assertEqual("main", source.metadata["sourceRepository"]["branch"])
        self.assertNotIn(TOKEN, metadata)
        self.assertNotIn("connectionId", metadata)
        self.assertNotIn("cloneUrl", metadata)

    def test_uses_source_commit_over_binding_head_commit(self) -> None:
        metadata_commit = "b" * 40
        task = _task(
            binding=_binding(headCommit="c" * 40),
            metadata={
                "sourceRepository": {
                    "repositoryId": "repo-1",
                    "commit": metadata_commit,
                    "branch": "main",
                },
                "sourceCommit": metadata_commit,
            },
        )
        runner = _FakeGitRunner(head=metadata_commit)

        source = self._prepare(task, runner=runner)

        self.assertEqual(metadata_commit, source.commit)
        checkout = next(call for call in runner.calls if call["args"][0] == "checkout")
        self.assertEqual(["checkout", "--detach", metadata_commit], checkout["args"])

    def test_falls_back_to_binding_head_commit(self) -> None:
        task = _task(metadata={"sourceCommit": "", "sourceRepository": {}})

        source = self._prepare(task)

        self.assertEqual(COMMIT, source.commit)

    def test_rejects_missing_credentials(self) -> None:
        with self.assertRaisesRegex(RepositorySourceError, "未匹配到 GitLab 凭据"):
            self._prepare(_task(), credentials=[])

    def test_rejects_missing_pinned_commit(self) -> None:
        task = _task(
            binding=_binding(headCommit=""),
            metadata={"sourceCommit": "", "sourceRepository": {}},
        )
        with self.assertRaisesRegex(RepositorySourceError, "缺少固定 commit"):
            self._prepare(task)

    def test_rejects_profile_error_repository(self) -> None:
        task = _task(binding=_binding(profileError="工作分支不存在或无权限"))

        with self.assertRaisesRegex(RepositorySourceError, "工作分支不存在或无权限"):
            self._prepare(task)

    def test_rejects_multiple_bindings(self) -> None:
        task = _task(bindings=[_binding(), _binding(bindingId="binding-2", repositoryId="repo-2")])

        with self.assertRaisesRegex(RepositorySourceError, "只支持一个仓库来源"):
            self._prepare(task)

    def test_rejects_repository_mismatch_against_source_metadata(self) -> None:
        task = _task()
        task.payload.metadata["sourceRepository"] = {"repositoryId": "repo-2"}

        with self.assertRaisesRegex(RepositorySourceError, "仓库来源与绑定仓库不一致"):
            self._prepare(task)

    def test_rejects_checkout_over_file_limit(self) -> None:
        runner = _FakeGitRunner(files={"a.ts": "a", "b.ts": "b", "c.ts": "c"})
        config = UiGenerationConfig(max_repo_files=2)

        with self.assertRaisesRegex(RepositorySourceError, "文件数超过上限"):
            self._prepare(_task(), runner=runner, config=config)

    def test_rejects_checkout_over_size_limit(self) -> None:
        runner = _FakeGitRunner(files={"large.bin": "x" * 2048})
        config = UiGenerationConfig(max_repo_size_mb=0.001)

        with self.assertRaisesRegex(RepositorySourceError, "大小超过上限"):
            self._prepare(_task(), runner=runner, config=config)

    def test_cleanup_deletes_success_and_retains_failure(self) -> None:
        source = self._prepare(_task())

        cleanup_repository_source(source, success=False, config=self.config)
        self.assertTrue(source.run_root.is_dir())
        self.assertTrue((source.run_root / ".retain-until").is_file())
        self.assertFalse((source.run_root / ".active").exists())

        cleanup_repository_source(source, success=True, config=self.config)
        self.assertFalse(source.run_root.exists())

    def test_real_git_clone_checks_out_pinned_commit_and_removes_git_dir(self) -> None:
        repo = Path(self.temp.name) / "source-repo"
        repo.mkdir()
        self._git(repo, "init", "-q", "-b", "main")
        self._git(repo, "config", "user.email", "tester@example.com")
        self._git(repo, "config", "user.name", "Tester")
        (repo / "index.html").write_text("pinned\n", encoding="utf-8")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-qm", "pinned")
        pinned = self._git(repo, "rev-parse", "HEAD").strip()
        (repo / "index.html").write_text("newer\n", encoding="utf-8")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-qm", "newer")

        task = _task(
            binding=_binding(
                instanceUrl="",
                cloneUrl=str(repo),
                branch="main",
                headCommit=pinned,
            ),
            metadata={
                "sourceRepository": {"repositoryId": "repo-1", "commit": pinned},
                "sourceCommit": pinned,
            },
        )
        with patch.object(
            git_workspace_module,
            "authenticated_clone_url",
            side_effect=lambda url: url,
        ):
            source = prepare_repository_source(
                task,
                _credentials(),
                agent_config=self.agent_config,
                config=self.config,
            )

        self.assertEqual(pinned, source.commit)
        self.assertEqual("pinned\n", (source.source_root / "index.html").read_text("utf-8"))
        self.assertFalse((source.source_root / ".git").exists())

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        ).stdout


class CredentialsFetcherTests(unittest.TestCase):
    def test_fetches_credentials_from_task_url(self) -> None:
        class Client:
            def get(self, path: str):
                self.path = path
                return {
                    "credentials": [
                        {
                            "connectionId": "conn-1",
                            "baseUrl": "https://gitlab.example.com",
                            "accessToken": TOKEN,
                            "repositoryIds": ["repo-1"],
                        }
                    ]
                }

        client = Client()
        credentials = build_credentials_fetcher(client)(_task())

        self.assertEqual("/internal/ai-worker/tasks/task-1/gitlab-credentials", client.path)
        self.assertEqual(TOKEN, credentials[0].access_token)
        self.assertEqual(["repo-1"], credentials[0].repository_ids)

    def test_rejects_missing_credentials_url(self) -> None:
        class Client:
            def get(self, path: str):
                raise AssertionError("credential endpoint must not be called")

        with self.assertRaisesRegex(RepositorySourceError, "gitlabCredentialsUrl"):
            build_credentials_fetcher(Client())(_task(gitlab_credentials_url=""))


class UiGenerationConfigTests(unittest.TestCase):
    def test_defaults_are_safe(self) -> None:
        config = Settings().ui_generation

        self.assertEqual(300.0, config.git_timeout_seconds)
        self.assertEqual(24.0, config.workspace_retention_hours)
        self.assertEqual(500.0, config.max_repo_size_mb)
        self.assertEqual(200_000, config.max_repo_files)

    def test_limits_are_overridable_via_toml(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as file:
            file.write(
                "[ui_generation]\n"
                "git_timeout_seconds = 30\n"
                "workspace_retention_hours = 2\n"
                "max_repo_size_mb = 50\n"
                "max_repo_files = 1000\n"
            )
            config_path = file.name
        try:
            settings = load_settings(config_path)
        finally:
            Path(config_path).unlink(missing_ok=True)

        config = settings.ui_generation
        self.assertEqual(30.0, config.git_timeout_seconds)
        self.assertEqual(2.0, config.workspace_retention_hours)
        self.assertEqual(50.0, config.max_repo_size_mb)
        self.assertEqual(1000, config.max_repo_files)


if __name__ == "__main__":
    unittest.main()
