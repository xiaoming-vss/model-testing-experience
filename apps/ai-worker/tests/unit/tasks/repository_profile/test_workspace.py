import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.config.models import PiConfig, RepositoryProfileConfig
from testing_agent_ai_worker.models.task import (
    GitlabCredentials,
    RepositoryBinding,
    RequirementInput,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks.git_workspace import GitWorkspaceError
from testing_agent_ai_worker.tasks.repository_profile.workspace import (
    ProfileWorkspaceError,
    cleanup_profile_workspace,
    prepare_profile_workspace,
)


def _task(*bindings: RepositoryBinding) -> Task:
    return Task(
        task_id="task-1",
        attempt_id="run-1",
        task_type="repository_profile",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="req-1",
        requirement_input=RequirementInput(
            requirementId="req-1",
            name="登录需求",
            documentType="richtext",
            documentContent="需求理解正文",
        ),
        bindings=list(bindings),
        payload=TaskPayload(openapi_content=""),
    )


def _binding(
    repository_id: str,
    *,
    clone_url: str | None = None,
    head_commit: str = "def456",
    profile_error: str = "",
) -> RepositoryBinding:
    return RepositoryBinding.model_validate(
        {
            "bindingId": f"binding-{repository_id}",
            "repositoryId": repository_id,
            "instanceUrl": "https://gitlab.example.com",
            "pathWithNamespace": f"team/{repository_id}",
            "cloneUrl": clone_url
            if clone_url is not None
            else f"https://gitlab.example.com/team/{repository_id}.git",
            "branch": "feature/login",
            "headCommit": head_commit,
            "connectionId": f"conn-{repository_id}",
            "profileError": profile_error,
        }
    )


def _credentials(*repository_ids: str) -> list[GitlabCredentials]:
    return [
        GitlabCredentials(
            connection_id=f"conn-{repository_id}",
            base_url="https://gitlab.example.com",
            access_token=f"secret-{repository_id}",
            repository_ids=[repository_id],
        )
        for repository_id in repository_ids
    ]


class _FakeGitRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.head = "def456"

    def run(self, args, *, cwd=None, env=None, timeout=300.0):
        self.calls.append({"args": list(args), "cwd": cwd, "env": env})
        if args[0] == "clone":
            if "bad-repo" in args[-2]:
                raise GitWorkspaceError("clone failed")
            repo = Path(args[-1])
            (repo / "src").mkdir(parents=True, exist_ok=True)
            (repo / "README.md").write_text("readme\n", encoding="utf-8")
            return ""
        if args[0] == "rev-parse":
            return f"{self.head}\n"
        return ""


class RepositoryProfileWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent_config = PiConfig(runtime_root=self.temp.name)
        self.config = RepositoryProfileConfig()

    def test_clones_only_working_branch_head_and_lists_top_level_entries(self) -> None:
        runner = _FakeGitRunner()
        workspace = prepare_profile_workspace(
            _task(_binding("repo-1")),
            _credentials("repo-1"),
            agent_config=self.agent_config,
            config=self.config,
            runner=runner,
        )

        self.assertEqual(1, len(workspace.repositories))
        self.assertEqual("def456", workspace.repositories[0].head_commit)
        self.assertEqual(
            ["src/", "README.md"],
            workspace.repositories[0].top_level_entries,
        )
        self.assertFalse(any(call["args"][0] == "diff" for call in runner.calls))
        clone_call = next(call for call in runner.calls if call["args"][0] == "clone")
        self.assertIn("oauth2@gitlab.example.com", clone_call["args"][-2])
        self.assertNotIn("secret-repo-1", " ".join(clone_call["args"]))

    def test_one_repository_failure_keeps_the_other_readable(self) -> None:
        runner = _FakeGitRunner()
        workspace = prepare_profile_workspace(
            _task(_binding("bad-repo"), _binding("repo-1")),
            _credentials("bad-repo", "repo-1"),
            agent_config=self.agent_config,
            config=self.config,
            runner=runner,
        )

        self.assertEqual(
            ["repo-1"], [repo.binding.repository_id for repo in workspace.repositories]
        )
        self.assertEqual(
            ["bad-repo"],
            [item.binding.repository_id for item in workspace.unavailable],
        )

    def test_profile_error_skips_repository_without_cloning(self) -> None:
        runner = _FakeGitRunner()
        workspace = prepare_profile_workspace(
            _task(_binding("repo-1", profile_error="无权限"), _binding("repo-2")),
            _credentials("repo-2"),
            agent_config=self.agent_config,
            config=self.config,
            runner=runner,
        )

        self.assertEqual(
            ["repo-2"], [repo.binding.repository_id for repo in workspace.repositories]
        )
        self.assertEqual(
            ["repo-1"],
            [item.binding.repository_id for item in workspace.unavailable],
        )

    def test_all_repositories_unavailable_fails(self) -> None:
        runner = _FakeGitRunner()
        with self.assertRaisesRegex(ProfileWorkspaceError, "所有绑定仓库均无法读取"):
            prepare_profile_workspace(
                _task(_binding("repo-1", profile_error="无权限")),
                [],
                agent_config=self.agent_config,
                config=self.config,
                runner=runner,
            )

    def test_manifest_excludes_credentials(self) -> None:
        workspace = prepare_profile_workspace(
            _task(_binding("repo-1")),
            _credentials("repo-1"),
            agent_config=self.agent_config,
            config=self.config,
            runner=_FakeGitRunner(),
        )
        manifest = json.dumps(workspace.manifest)
        self.assertNotIn("secret-repo-1", manifest)
        self.assertNotIn("accessToken", manifest)

    def test_cleanup_deletes_success_and_retains_failure(self) -> None:
        workspace = prepare_profile_workspace(
            _task(_binding("repo-1")),
            _credentials("repo-1"),
            agent_config=self.agent_config,
            config=self.config,
            runner=_FakeGitRunner(),
        )
        cleanup_profile_workspace(workspace, success=False, config=self.config)
        self.assertTrue((workspace.run_root / ".retain-until").exists())
        self.assertTrue(workspace.run_root.exists())
        cleanup_profile_workspace(workspace, success=True, config=self.config)
        self.assertFalse(workspace.run_root.exists())

    def test_missing_head_commit_marks_unavailable(self) -> None:
        workspace = prepare_profile_workspace(
            _task(_binding("repo-1", head_commit=""), _binding("repo-2")),
            _credentials("repo-1", "repo-2"),
            agent_config=self.agent_config,
            config=self.config,
            runner=_FakeGitRunner(),
        )
        self.assertEqual(
            ["repo-2"], [repo.binding.repository_id for repo in workspace.repositories]
        )
        self.assertEqual(["repo-1"], [item.binding.repository_id for item in workspace.unavailable])


if __name__ == "__main__":
    unittest.main()
