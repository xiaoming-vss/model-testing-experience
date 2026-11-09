import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.models.task import RepositoryBinding
from testing_agent_ai_worker.tasks.repository_profile.contracts import (
    ProfileContractError,
    validate_profile_output,
)
from testing_agent_ai_worker.tasks.repository_profile.workspace import (
    ProfileRepoWorkspace,
    ProfileWorkspace,
    UnavailableRepository,
)


def _binding(repository_id: str, path: str | None = None) -> RepositoryBinding:
    return RepositoryBinding.model_validate(
        {
            "bindingId": f"binding-{repository_id}",
            "repositoryId": repository_id,
            "pathWithNamespace": path or f"team/{repository_id}",
            "branch": "feature/login",
            "headCommit": "def456",
        }
    )


def _repo(root: Path, binding: RepositoryBinding, order: int) -> ProfileRepoWorkspace:
    repo_path = root / binding.repository_id
    (repo_path / "src").mkdir(parents=True, exist_ok=True)
    (repo_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return ProfileRepoWorkspace(
        binding=binding,
        path=repo_path,
        head_commit=binding.head_commit,
        order=order,
        top_level_entries=["src/", "pom.xml"],
    )


def _valid_repository(repository_id: str) -> dict:
    return {
        "repositoryId": repository_id,
        "pathWithNamespace": f"team/{repository_id}",
        "role": "backend",
        "responsibilitySummary": "提供登录接口",
        "techStack": ["Java", "Spring Boot"],
        "keyPaths": ["src"],
        "confidence": 0.86,
        "evidence": ["pom.xml"],
    }


class RepositoryProfileContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binding = _binding("repo-1")
        self.repo = _repo(self.root, self.binding, 0)
        self.workspace = ProfileWorkspace(
            run_root=self.root,
            code_root=self.root,
            repositories=[self.repo],
            unavailable=[],
        )

    def _validate(self, data: dict) -> dict:
        return validate_profile_output(
            json.dumps(data, ensure_ascii=False),
            self.workspace,
            max_output_chars=100_000,
        )

    def test_valid_output_is_canonical(self) -> None:
        result = self._validate(
            {"repositories": [_valid_repository("repo-1")], "overallSummary": "后端仓库"}
        )
        self.assertEqual("repo-1", result["repositories"][0]["repositoryId"])
        self.assertEqual(0.86, result["repositories"][0]["confidence"])

    def test_unavailable_repository_is_appended_in_original_order(self) -> None:
        unavailable_binding = _binding("repo-2")
        workspace = ProfileWorkspace(
            run_root=self.root,
            code_root=self.root,
            repositories=[self.repo],
            unavailable=[UnavailableRepository(unavailable_binding, "无权限", 1)],
        )
        result = validate_profile_output(
            json.dumps(
                {"repositories": [_valid_repository("repo-1")], "overallSummary": "后端仓库"},
                ensure_ascii=False,
            ),
            workspace,
            max_output_chars=100_000,
        )
        self.assertEqual(
            ["repo-1", "repo-2"], [item["repositoryId"] for item in result["repositories"]]
        )
        self.assertEqual("unknown", result["repositories"][1]["role"])
        self.assertEqual(0, result["repositories"][1]["confidence"])
        self.assertEqual([], result["repositories"][1]["evidence"])

    def test_rejects_fence(self) -> None:
        text = (
            "```json\n"
            + json.dumps(
                {"repositories": [_valid_repository("repo-1")], "overallSummary": "后端仓库"}
            )
            + "\n```"
        )
        with self.assertRaisesRegex(ProfileContractError, "Markdown"):
            validate_profile_output(text, self.workspace, max_output_chars=100_000)

    def test_rejects_extra_top_level_field(self) -> None:
        with self.assertRaisesRegex(ProfileContractError, "顶层字段"):
            self._validate(
                {
                    "repositories": [_valid_repository("repo-1")],
                    "overallSummary": "后端仓库",
                    "analyzedAt": "now",
                }
            )

    def test_rejects_extra_repository_field(self) -> None:
        item = _valid_repository("repo-1")
        item["branch"] = "feature/login"
        with self.assertRaisesRegex(ProfileContractError, "仓库条目字段"):
            self._validate({"repositories": [item], "overallSummary": "后端仓库"})

    def test_rejects_duplicate_json_key(self) -> None:
        text = '{"repositories": [], "repositories": [], "overallSummary": "后端仓库"}'
        with self.assertRaisesRegex(ProfileContractError, "重复 JSON 字段"):
            validate_profile_output(text, self.workspace, max_output_chars=100_000)

    def test_rejects_nan(self) -> None:
        text = json.dumps(
            {"repositories": [_valid_repository("repo-1")], "overallSummary": "后端仓库"}
        ).replace("0.86", "NaN")
        with self.assertRaisesRegex(ProfileContractError, "非法 JSON 数值"):
            validate_profile_output(text, self.workspace, max_output_chars=100_000)

    def test_rejects_missing_repository(self) -> None:
        with self.assertRaisesRegex(ProfileContractError, "缺少仓库画像"):
            self._validate({"repositories": [], "overallSummary": "后端仓库"})

    def test_rejects_duplicate_repository(self) -> None:
        with self.assertRaisesRegex(ProfileContractError, "仓库重复输出"):
            self._validate(
                {
                    "repositories": [
                        _valid_repository("repo-1"),
                        _valid_repository("repo-1"),
                    ],
                    "overallSummary": "后端仓库",
                }
            )

    def test_rejects_invalid_role(self) -> None:
        item = _valid_repository("repo-1")
        item["role"] = "mobile"
        with self.assertRaisesRegex(ProfileContractError, "仓库角色不合法"):
            self._validate({"repositories": [item], "overallSummary": "后端仓库"})

    def test_unknown_requires_zero_confidence_and_empty_evidence(self) -> None:
        item = _valid_repository("repo-1")
        item["role"] = "unknown"
        item["confidence"] = 0.4
        item["evidence"] = []
        with self.assertRaisesRegex(ProfileContractError, "unknown 仓库置信度"):
            self._validate({"repositories": [item], "overallSummary": "后端仓库"})

    def test_known_role_requires_evidence(self) -> None:
        item = _valid_repository("repo-1")
        item["evidence"] = []
        with self.assertRaisesRegex(ProfileContractError, "缺少 evidence"):
            self._validate({"repositories": [item], "overallSummary": "后端仓库"})

    def test_key_path_must_exist_inside_repository(self) -> None:
        item = _valid_repository("repo-1")
        item["keyPaths"] = ["../outside"]
        with self.assertRaisesRegex(ProfileContractError, "keyPaths"):
            self._validate({"repositories": [item], "overallSummary": "后端仓库"})

    def test_rejects_too_many_items(self) -> None:
        item = _valid_repository("repo-1")
        item["techStack"] = ["a", "b", "c", "d", "e", "f"]
        with self.assertRaisesRegex(ProfileContractError, "最多 5 项"):
            self._validate({"repositories": [item], "overallSummary": "后端仓库"})


if __name__ == "__main__":
    unittest.main()
