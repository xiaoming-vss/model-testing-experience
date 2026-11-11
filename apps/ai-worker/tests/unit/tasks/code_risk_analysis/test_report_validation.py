import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.models.task import RepositoryBinding
from testing_agent_ai_worker.tasks.code_risk_analysis.report_validation import (
    RiskReportValidationError,
    validate_risk_report,
)
from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import CodeWorkspace, RepoWorkspace


class ReportValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        code = root / "code"
        repo_path = code / "repo"
        (repo_path / "src").mkdir(parents=True)
        (repo_path / "src" / "login.py").write_text("x", encoding="utf-8")
        binding = RepositoryBinding.model_validate(
            {
                "bindingId": "b1",
                "repositoryId": "repo-1",
                "branch": "feature/login",
                "baselineBranch": "main",
            }
        )
        self.workspace = CodeWorkspace(
            run_root=root,
            code_root=code,
            repositories=[
                RepoWorkspace(
                    binding=binding,
                    path=repo_path,
                    base_commit="base",
                    head_commit="head",
                    changed_files=["src/login.py"],
                    diff_files=[],
                    files_changed=1,
                    additions=1,
                    deletions=0,
                )
            ],
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_accepts_report_and_rejects_unknown_case_or_path(self):
        report = """changeOverview: {}\nrisks:\n  - level: high\n    reason: auth changed\n    location: src/login.py\n    impact: login\n    evidence: [src/login.py]\naffectedCases:\n  - caseId: c1\n    impact: changed\ncoverageGaps:\n  - gap: missing failure path\n    suggestion: add test\n"""
        result = validate_risk_report(report, self.workspace, expected_case_ids={"c1"})
        self.assertEqual("c1", result["affectedCases"][0]["caseId"])

        with self.assertRaises(RiskReportValidationError) as error:
            validate_risk_report(
                report.replace("c1", "unknown"), self.workspace, expected_case_ids={"c1"}
            )
        self.assertIn("unknown_case_id", str(error.exception))

    def test_rejects_missing_evidence(self):
        with self.assertRaises(RiskReportValidationError) as error:
            validate_risk_report(
                "changeOverview: {}\nrisks:\n  - level: high\n    reason: bad\n    location: src/login.py\n    impact: bad\naffectedCases: []\ncoverageGaps: []\n",
                self.workspace,
                expected_case_ids=set(),
            )
        self.assertIn("missing_evidence", str(error.exception))
