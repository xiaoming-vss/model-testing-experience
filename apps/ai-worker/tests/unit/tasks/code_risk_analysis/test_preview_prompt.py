import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.models.task import RepositoryBinding
from testing_agent_ai_worker.tasks.code_risk_analysis.context import ContextPackage
from testing_agent_ai_worker.tasks.code_risk_analysis.preview_prompt import (
    ContextReceiptError,
    build_preview_prompt,
    build_result_receipt,
    validate_context_receipt,
)
from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import (
    CodeWorkspace,
    RepoWorkspace,
)

VALID_RECEIPT = """\
analyzedAt: "2026-08-27T10:00:00+08:00"
contextReceipt:
  receivedRepositories:
    - repositoryId: repo-1
      headCommit: def456
    - repositoryId: repo-2
      headCommit: 222
  summary: 已读取两个仓库
  filesRead:
    - src/login.py
  toolsUsed:
    - read
    - grep
"""


class PreviewPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.code_root = root / "code"
        self.repositories = []
        for index, (repository_id, head) in enumerate((("repo-1", "def456"), ("repo-2", "222"))):
            path = self.code_root / "repos" / f"repo-{index}"
            path.mkdir(parents=True)
            self.repositories.append(
                RepoWorkspace(
                    binding=RepositoryBinding(
                        binding_id=f"b-{index}",
                        repository_id=repository_id,
                        path_with_namespace=f"team/{repository_id}",
                        branch="feature",
                        baseline_branch="release",
                        base_commit="base",
                        head_commit=head,
                    ),
                    path=path,
                    base_commit="base",
                    head_commit=head,
                    changed_files=["src/login.py"],
                    diff_files=[],
                    files_changed=1,
                    additions=1,
                    deletions=0,
                )
            )
        self.workspace = CodeWorkspace(
            run_root=root, code_root=self.code_root, repositories=self.repositories
        )
        self.context = ContextPackage(
            text="固定上下文正文",
            manifest={"repositories": self.workspace.manifest["repositories"]},
            diff_chars=123,
            truncated_files=["src/big.py"],
        )

    def test_prompt_declares_preview_mode_workspace_and_limits(self) -> None:
        prompt = build_preview_prompt(self.context, self.workspace)

        self.assertIn("上下文预览助手", prompt)
        self.assertIn(str(self.code_root), prompt)
        self.assertIn("固定上下文正文", prompt)
        self.assertIn("read/grep/find/ls", prompt)
        self.assertIn("不允许修改文件", prompt)

    def test_validates_complete_receipt(self) -> None:
        receipt = validate_context_receipt(VALID_RECEIPT, self.workspace)

        self.assertEqual("已读取两个仓库", receipt["summary"])
        self.assertEqual(["src/login.py"], receipt["filesRead"])
        self.assertEqual(["read", "grep"], receipt["toolsUsed"])
        self.assertEqual(2, len(receipt["receivedRepositories"]))

    def test_strips_yaml_fence_and_accepts_snake_case(self) -> None:
        receipt = validate_context_receipt(
            "```yaml\n"
            "context_receipt:\n"
            "  received_repositories:\n"
            "    - repository_id: repo-1\n"
            "      head_commit: def456\n"
            "    - repository_id: repo-2\n"
            "      head_commit: '222'\n"
            "  summary: ok\n"
            "  files_read: []\n"
            "  tools_used: []\n"
            "```",
            self.workspace,
        )

        self.assertEqual("ok", receipt["summary"])
        self.assertEqual([], receipt["filesRead"])

    def test_rejects_empty_or_non_object_output(self) -> None:
        for raw in ("", "   ", "- a\n- b\n", "not: [valid"):
            with self.subTest(raw=raw), self.assertRaises(ContextReceiptError):
                validate_context_receipt(raw, self.workspace)

    def test_rejects_missing_receipt_summary_or_repositories(self) -> None:
        for raw in (
            "analyzedAt: now\n",
            "contextReceipt: []\n",
            "contextReceipt:\n  receivedRepositories:\n    - repositoryId: repo-1\n",
            "contextReceipt:\n  summary: ok\n",
            "contextReceipt:\n  summary: '  '\n  receivedRepositories: []\n",
            "contextReceipt:\n  summary: ok\n  receivedRepositories: [{}]\n",
        ):
            with self.subTest(raw=raw), self.assertRaises(ContextReceiptError):
                validate_context_receipt(raw, self.workspace)

    def test_rejects_incomplete_or_wrong_repositories(self) -> None:
        cases = (
            # Missing repo-2.
            "contextReceipt:\n"
            "  summary: ok\n"
            "  receivedRepositories:\n"
            "    - repositoryId: repo-1\n"
            "      headCommit: def456\n",
            # Wrong head commit.
            "contextReceipt:\n"
            "  summary: ok\n"
            "  receivedRepositories:\n"
            "    - repositoryId: repo-1\n"
            "      headCommit: wrong\n"
            "    - repositoryId: repo-2\n"
            "      headCommit: '222'\n",
        )
        for raw in cases:
            with (
                self.subTest(raw=raw),
                self.assertRaisesRegex(ContextReceiptError, "未收到完整仓库上下文"),
            ):
                validate_context_receipt(raw, self.workspace)

    def test_rejects_invalid_file_or_tool_lists(self) -> None:
        base = VALID_RECEIPT.replace(
            "  filesRead:\n    - src/login.py\n", "  filesRead: not-a-list\n"
        )
        with self.assertRaisesRegex(ContextReceiptError, "filesRead"):
            validate_context_receipt(base, self.workspace)
        base = VALID_RECEIPT.replace(
            "  toolsUsed:\n    - read\n    - grep\n", "  toolsUsed:\n    - 1\n"
        )
        with self.assertRaisesRegex(ContextReceiptError, "toolsUsed"):
            validate_context_receipt(base, self.workspace)

    def test_result_receipt_merges_workspace_facts(self) -> None:
        model_receipt = validate_context_receipt(VALID_RECEIPT, self.workspace)

        result = build_result_receipt(self.workspace, self.context, model_receipt)

        self.assertEqual("context_preview", result["contextReceipt"]["mode"])
        self.assertEqual(2, result["contextReceipt"]["counts"]["repositories"])
        self.assertEqual(2, result["contextReceipt"]["counts"]["changedFiles"])
        self.assertEqual(123, result["contextReceipt"]["counts"]["diffChars"])
        self.assertEqual(["src/big.py"], result["contextReceipt"]["truncatedFiles"])
        self.assertEqual(2, len(result["contextReceipt"]["repositories"]))
        self.assertEqual("已读取两个仓库", result["contextReceipt"]["summary"])
        self.assertTrue(result["analyzedAt"])


if __name__ == "__main__":
    unittest.main()
