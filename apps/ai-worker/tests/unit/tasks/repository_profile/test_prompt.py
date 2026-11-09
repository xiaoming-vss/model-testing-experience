import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.models.task import (
    RepositoryBinding,
    RequirementInput,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.tasks.repository_profile.context import build_profile_context
from testing_agent_ai_worker.tasks.repository_profile.prompt import build_profile_prompt
from testing_agent_ai_worker.tasks.repository_profile.workspace import (
    ProfileRepoWorkspace,
    ProfileWorkspace,
    UnavailableRepository,
)


class RepositoryProfilePromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        binding = RepositoryBinding.model_validate(
            {
                "bindingId": "binding-repo-1",
                "repositoryId": "repo-1",
                "pathWithNamespace": "team/repo-1",
                "branch": "feature/login",
                "headCommit": "def456",
            }
        )
        unavailable = RepositoryBinding.model_validate(
            {
                "bindingId": "binding-repo-2",
                "repositoryId": "repo-2",
                "pathWithNamespace": "team/repo-2",
                "branch": "feature/login",
            }
        )
        repo_path = self.root / "repo-1"
        repo_path.mkdir()
        (repo_path / "src").mkdir()
        (repo_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        self.workspace = ProfileWorkspace(
            run_root=self.root,
            code_root=self.root,
            repositories=[
                ProfileRepoWorkspace(
                    binding=binding,
                    path=repo_path,
                    head_commit="def456",
                    order=0,
                    top_level_entries=["src/", "pom.xml"],
                )
            ],
            unavailable=[UnavailableRepository(unavailable, "无权限", 1)],
        )
        self.task = Task(
            task_id="task-1",
            task_type="repository_profile",
            requirement_input=RequirementInput(
                requirementId="req-1",
                name="登录需求",
                documentType="richtext",
                documentContent="需求理解正文",
            ),
            payload=TaskPayload(openapi_content=""),
        )

    def test_context_contains_understanding_and_repository_manifest(self) -> None:
        context = build_profile_context(self.task, self.workspace)
        self.assertIn("需求理解正文", context.text)
        self.assertIn("repo-1", context.text)
        self.assertIn("src/", context.text)
        self.assertIn("repo-2", context.text)
        self.assertIn("不要为它们输出", context.text)

    def test_prompt_contains_exact_contract_and_read_only_rules(self) -> None:
        context = build_profile_context(self.task, self.workspace)
        prompt = build_profile_prompt(context, self.workspace)
        self.assertIn(str(self.root), prompt)
        self.assertIn("read/grep/find/ls", prompt)
        self.assertIn("只输出一个 JSON 对象", prompt)
        self.assertIn("responsibilitySummary", prompt)
        self.assertIn("unknown", prompt)
        self.assertIn("不得增加任何字段", prompt)


if __name__ == "__main__":
    unittest.main()
