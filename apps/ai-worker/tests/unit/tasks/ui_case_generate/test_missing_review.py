import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from testing_agent_ai_worker.tasks.ui_case_generate.executor import _validate_ui_stage_yaml
from testing_agent_ai_worker.tasks.ui_case_generate.missing_review import review_issues
from testing_agent_ai_worker.tasks.ui_case_generate.yaml_batches import generate_yaml_batches
from tests.unit.tasks.ui_case_generate import test_yaml_batches


class MissingReviewTests(unittest.TestCase):
    def run_review(self, response, *, bad_candidate=False):
        fixtures = test_yaml_batches.YamlBatchTests()
        body = fixtures.body()
        calls, reviews, reports = [], [], []

        def generate(prompt, batch, rules):
            data, _ = json.JSONDecoder().raw_decode(prompt)
            calls.append(batch)
            return (
                "invalid"
                if bad_candidate
                else yaml.safe_dump(fixtures.candidate(data["design"]["cases"]))
            )

        def review(prompt, batch, rules):
            reviews.append(batch)
            self.assertTrue((Path(root) / "candidate.yaml").is_file())
            if isinstance(response, BaseException):
                raise response
            return response

        with tempfile.TemporaryDirectory() as root:
            result = asyncio.run(
                generate_yaml_batches(
                    body=body,
                    generate=generate,
                    review=review,
                    review_report=reports.append,
                    instruction="",
                    user_instruction="",
                    diagnostic_dir=Path(root),
                    report=lambda _: None,
                    validate_yaml=_validate_ui_stage_yaml,
                )
            )
            self.assertEqual((Path(root) / "candidate.yaml").read_text(), result)
        return result, calls, reviews, reports

    def test_semantic_findings_are_published_without_regenerating(self):
        issue = dict(
            caseIndex=1,
            stepIndex=1,
            code="runtime_value",
            evidence="本次新建对象的 ID 被要求预先填写",
            repair="核查提取与引用",
        )
        result, calls, reviews, reports = self.run_review(json.dumps({"issues": [issue]}))
        self.assertEqual(len(yaml.safe_load(result)), 3)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(reviews, [1, 2])
        self.assertEqual(reports[0]["status"], "completed")
        self.assertEqual(len(reports[0]["modules"]), 2)
        # Positions refer to the merged draft, even when source modules interleave.
        names = [row["name"] for row in yaml.safe_load(result)]
        for module in reports[0]["modules"]:
            issue = module["issues"][0]
            self.assertEqual(names[issue["caseIndex"] - 1], issue["caseName"])
        from hashlib import sha256

        self.assertEqual(reports[0]["artifactSha256"], sha256(result.encode()).hexdigest())

    def test_invalid_review_is_repaired_once_without_rewriting_yaml(self):
        result, calls, reviews, reports = self.run_review("not json")
        self.assertEqual(len(yaml.safe_load(result)), 3)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(reviews, [1, 1, 2, 2])
        self.assertEqual(reports[0]["status"], "incomplete")
        self.assertTrue(all(m["errorCode"] == "invalid_report" for m in reports[0]["modules"]))

    def test_review_call_failure_and_timeout_keep_draft(self):
        for error, code in [
            (RuntimeError("private provider detail"), "model_error"),
            (TimeoutError(), "timeout"),
        ]:
            with self.subTest(code=code):
                result, calls, reviews, reports = self.run_review(error)
                self.assertEqual(len(yaml.safe_load(result)), 3)
                self.assertEqual(calls, [1, 2])
                self.assertEqual(reviews, [1, 2])
                self.assertEqual(reports[0]["status"], "incomplete")
                self.assertEqual(reports[0]["modules"][0]["errorCode"], code)
                self.assertNotIn("private provider detail", json.dumps(reports))

    def test_cancellation_and_permission_failures_are_not_swallowed(self):
        for error in (asyncio.CancelledError(), PermissionError()):
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                self.run_review(error)

    def test_invalid_yaml_still_fails(self):
        with self.assertRaisesRegex(ValueError, "共 3 次调用"):
            self.run_review('{"issues": []}', bad_candidate=True)

    def test_review_timeout_cancels_inflight_call(self):
        from unittest.mock import patch

        from testing_agent_ai_worker.tasks.ui_case_generate import missing_review

        canceled = []

        async def slow(*args):
            try:
                await asyncio.sleep(60)
            finally:
                canceled.append(True)

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(missing_review, "REVIEW_TIMEOUT_SECONDS", 0.01),
        ):
            result = asyncio.run(
                missing_review.check_missing_semantics(
                    raw="- stepsJson: [{}]",
                    inputs={},
                    generate=slow,
                    diagnostic_dir=Path(root),
                )
            )
        self.assertEqual(result["errorCode"], "timeout")
        self.assertEqual(canceled, [True])

    def test_review_requires_real_step_and_evidence(self):
        rows = [{"stepsJson": [{}]}]
        self.assertEqual(review_issues('{"issues": []}', rows), [])
        for issue in (
            {},
            dict(caseIndex=2, stepIndex=1, code="identity", evidence="e", repair="r"),
        ):
            with self.assertRaises(ValueError):
                review_issues(json.dumps({"issues": [issue]}), rows)

    def test_wrong_step_feedback_identifies_case_and_valid_range(self):
        issue = dict(
            caseIndex=1, stepIndex=28, code="coverage", evidence="遗漏字段", repair="保留目标"
        )
        with self.assertRaisesRegex(ValueError, r"issues\[1\].stepIndex: 候选用例 1 仅有 27 步"):
            review_issues(json.dumps({"issues": [issue]}), [{"stepsJson": [{}] * 27}])
