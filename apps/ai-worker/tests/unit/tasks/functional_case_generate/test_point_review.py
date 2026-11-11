import json
import unittest

from testing_agent_ai_worker.tasks.functional_case_generate.point_review import (
    generate_reviewed_points,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import OutputValidationError
from tests.unit.tasks.functional_case_generate.fixtures import points


class PointReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_audit_and_correction_preserve_input_and_return_only_corrected_result(self):
        draft = points()
        corrected = points()
        corrected["categories"][0]["data"][0]["test_points"][0]["case_name"] = "验证有效条件下登录"
        calls = []

        async def generate(prompt, phase):
            calls.append((phase, prompt))
            if phase == "generate":
                return json.dumps(draft, ensure_ascii=False)
            if phase == "audit-conditions-0":
                return json.dumps(
                    {"issues": [{"case_name": "验证登录", "problem": "缺少必要条件"}]},
                    ensure_ascii=False,
                )
            if phase == "correct-0":
                return json.dumps(corrected, ensure_ascii=False)
            return json.dumps({"issues": []})

        result = await generate_reviewed_points(
            generation_input="生成输入",
            evidence_input="原始需求与已审核分析",
            user_instruction="保留用户模块",
            generate=generate,
        )
        self.assertEqual(json.loads(result), corrected)
        self.assertEqual(
            [phase for phase, _ in calls],
            [
                "generate",
                "audit-conditions-0",
                "correct-0",
                "audit-conditions-1",
                "audit-coverage-1",
            ],
        )
        self.assertIn("原始需求与已审核分析", calls[1][1])
        self.assertIn("保留用户模块", calls[1][1])
        self.assertIn("缺少必要条件", calls[2][1])
        self.assertIn("验证登录", calls[2][1])

    async def test_clean_audit_returns_draft_without_correction(self):
        calls = []

        async def generate(prompt, phase):
            calls.append(phase)
            return json.dumps(points() if phase == "generate" else {"issues": []})

        result = await generate_reviewed_points(
            generation_input="输入", evidence_input="依据", user_instruction="", generate=generate
        )
        self.assertEqual(json.loads(result), points())
        self.assertEqual(calls, ["generate", "audit-conditions-0", "audit-coverage-0"])

    async def test_invalid_audit_never_exposes_unreviewed_draft(self):
        async def generate(prompt, phase):
            return json.dumps(points()) if phase == "generate" else "not-json"

        with self.assertRaises(OutputValidationError):
            await generate_reviewed_points(
                generation_input="输入",
                evidence_input="依据",
                user_instruction="",
                generate=generate,
            )

    async def test_conditions_are_checked_in_batches_before_coverage(self):
        draft = points()
        draft["categories"][0]["data"][0]["test_points"] = [
            {"case_name": f"验证条件 {i}"} for i in range(21)
        ]
        calls = []

        async def generate(prompt, phase):
            calls.append((phase, prompt))
            return json.dumps(draft if phase == "generate" else {"issues": []})

        result = await generate_reviewed_points(
            generation_input="输入",
            evidence_input="完整依据",
            user_instruction="",
            generate=generate,
        )
        self.assertEqual(json.loads(result), draft)
        audits = [(phase, prompt) for phase, prompt in calls if "audit-conditions" in phase]
        self.assertEqual(len(audits), 3)
        self.assertTrue(all("完整依据" in prompt for _, prompt in audits))
        self.assertIn("验证条件 0", audits[0][1])
        self.assertNotIn("验证条件 10", audits[0][1])
        self.assertEqual(calls[-1][0], "audit-coverage-0")

    async def test_coverage_issue_triggers_correction_and_both_rechecks(self):
        calls = []

        async def generate(prompt, phase):
            calls.append(phase)
            if phase == "audit-coverage-0":
                return json.dumps({"issues": [{"case_name": None, "problem": "遗漏独立结果"}]})
            if phase.startswith("audit-"):
                return json.dumps({"issues": []})
            return json.dumps(points())

        await generate_reviewed_points(
            generation_input="输入", evidence_input="依据", user_instruction="", generate=generate
        )
        self.assertEqual(
            calls,
            [
                "generate",
                "audit-conditions-0",
                "audit-coverage-0",
                "correct-0",
                "audit-conditions-1",
                "audit-coverage-1",
            ],
        )

    async def test_audit_cannot_modify_a_case_that_is_not_in_the_draft(self):
        calls = []

        async def generate(prompt, phase):
            calls.append(phase)
            if phase == "generate":
                return json.dumps(points())
            return json.dumps({"issues": [{"case_name": "不存在的测试点", "problem": "条件缺失"}]})

        with self.assertRaisesRegex(OutputValidationError, "不存在的测试点"):
            await generate_reviewed_points(
                generation_input="输入",
                evidence_input="依据",
                user_instruction="",
                generate=generate,
            )
        self.assertEqual(calls, ["generate", "audit-conditions-0"])

    async def test_persistent_findings_fail_after_bounded_corrections(self):
        calls = []

        async def generate(prompt, phase):
            calls.append(phase)
            if phase.startswith("audit-"):
                return json.dumps({"issues": [{"case_name": "验证登录", "problem": "条件缺失"}]})
            return json.dumps(points())

        with self.assertRaisesRegex(OutputValidationError, "3 次修订后仍未通过"):
            await generate_reviewed_points(
                generation_input="输入",
                evidence_input="依据",
                user_instruction="",
                generate=generate,
            )
        self.assertEqual(
            calls,
            [
                "generate",
                "audit-conditions-0",
                "correct-0",
                "audit-conditions-1",
                "correct-1",
                "audit-conditions-2",
                "correct-2",
                "audit-conditions-3",
            ],
        )
