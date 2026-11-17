import copy
import json
import unittest
from pathlib import Path

from testing_agent_ai_worker.requirement_artifacts import validate_artifact

APP = Path(__file__).resolve().parents[4]
ROOT = Path(__file__).resolve().parents[6]
FIXTURES = APP / "tests/fixtures/requirement_review"
WORKER_SCHEMA = APP / "src/testing_agent_ai_worker/requirement_schemas/requirement-review.schema.json"
CONTROL_PLANE_SCHEMA = (
    ROOT
    / "apps/control-plane/src/testing_agent/domain/requirement_schemas/requirement-review.schema.json"
)
SKILL_SCHEMA = (
    ROOT
    / "apps/control-plane/default-skills/mtx-review-requirement/references/output.schema.json"
)
CONTROL_PLANE_VALIDATOR = (
    ROOT / "apps/control-plane/src/testing_agent/domain/requirement_artifacts.py"
)
WORKER_VALIDATOR = APP / "src/testing_agent_ai_worker/requirement_artifacts.py"


def example(name):
    return json.loads((FIXTURES / f"{name}.example.json").read_text())


class ReviewArtifactTests(unittest.TestCase):
    def test_examples_validate(self):
        for name in ("blocked", "needs-clarification", "passed"):
            with self.subTest(name=name):
                self.assertEqual(
                    validate_artifact(example(name), "requirement_review"),
                    example(name),
                )

    def test_review_status_must_match_issue_severity(self):
        for source, status in (
            ("blocked", "passed"),
            ("passed", "blocked"),
            ("needs-clarification", "passed"),
        ):
            with self.subTest(source=source, status=status):
                data = example(source)
                data["reviewStatus"] = status
                with self.assertRaises(ValueError):
                    validate_artifact(data, "requirement_review")

    def test_blocker_requires_failure_mode(self):
        data = example("blocked")
        data["issues"][0].pop("failureMode")
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")

    def test_blocker_and_major_require_quoted_evidence(self):
        for source in ("blocked", "needs-clarification"):
            with self.subTest(source=source):
                data = example(source)
                data["issues"][0]["evidence"] = []
                with self.assertRaises(ValueError):
                    validate_artifact(data, "requirement_review")
                data = example(source)
                data["issues"][0]["evidence"][0]["quote"] = ""
                with self.assertRaises(ValueError):
                    validate_artifact(data, "requirement_review")

    def test_duplicate_issue_ids_are_rejected(self):
        data = example("blocked")
        data["issues"].append(copy.deepcopy(data["issues"][0]))
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")

    def test_coverage_references_existing_issues(self):
        data = example("blocked")
        data["coverage"]["smells"][0]["issueId"] = "RR-99"
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")
        data = example("blocked")
        data["coverage"]["qualityCharacteristics"][0]["issueIds"] = ["RR-99"]
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")
        data = example("blocked")
        data["coverage"]["traceability"][0]["issueId"] = "RR-99"
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")

    def test_quality_and_traceability_pass_fail_references_are_checked(self):
        data = example("blocked")
        data["coverage"]["qualityCharacteristics"][0]["status"] = "pass"
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")
        data = example("blocked")
        data["coverage"]["qualityCharacteristics"][0]["status"] = "fail"
        data["coverage"]["qualityCharacteristics"][0]["issueIds"] = []
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")
        data = example("passed")
        data["coverage"]["traceability"][0]["issueId"] = "RR-01"
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")
        data = example("blocked")
        data["coverage"]["traceability"][0].pop("issueId")
        with self.assertRaises(ValueError):
            validate_artifact(data, "requirement_review")

    def test_unknown_top_level_fields_are_rejected(self):
        for field in ("questions", "clarifications", "riskAcceptance"):
            with self.subTest(field=field):
                data = example("passed")
                data[field] = []
                with self.assertRaises(ValueError):
                    validate_artifact(data, "requirement_review")

    def test_schema_copies_are_identical(self):
        if not CONTROL_PLANE_SCHEMA.exists() or not SKILL_SCHEMA.exists():
            self.skipTest("control-plane or skill schema is not available")
        self.assertEqual(
            WORKER_SCHEMA.read_text(encoding="utf-8"),
            CONTROL_PLANE_SCHEMA.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            WORKER_SCHEMA.read_text(encoding="utf-8"),
            SKILL_SCHEMA.read_text(encoding="utf-8"),
        )

    def test_validator_copies_are_identical(self):
        if not CONTROL_PLANE_VALIDATOR.exists():
            self.skipTest("control-plane validator is not available")
        self.assertEqual(
            WORKER_VALIDATOR.read_text(encoding="utf-8"),
            CONTROL_PLANE_VALIDATOR.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
