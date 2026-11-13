"""Revision reviews must not repeat checks for unrelated, unchanged points."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker.tasks.functional_case_generate.traceable_review import (
    generate_traceable_points,
)
from testing_agent_ai_worker.tasks.functional_case_generate.validation import OutputValidationError
from tests.unit.tasks.functional_case_generate.fixtures import traceable_modules


class IncrementalReviewTest(unittest.IsolatedAsyncioTestCase):
    async def run_review(self, revise, *, followup=None, issue_kind="unsupported"):
        original = traceable_modules(*(f"模块{i}" for i in range(21)))
        for index, point in enumerate(original["testPoints"], 1):
            point["materialBlockIds"] = [f"B{index}"]
        issue = {
            "kind": issue_kind,
            "targetType": "missing" if issue_kind == "missing" else "testPoint",
            "targetId": None if issue_kind == "missing" else "P1",
            "issue": "需要核对 B1 的边界",
            "suggestion": "补充边界",
            **{k: v for k, v in original["testPoints"][0].items() if k.endswith("Ids")},
        }
        revised = revise(copy.deepcopy(original))
        seen = {}

        async def generate(prompt, phase):
            seen[phase] = prompt
            if phase == "generate":
                return json.dumps(original)
            if phase.startswith("correct"):
                return json.dumps(revised)
            if phase.startswith("audit-0-"):
                target_phase = "coverage" if issue_kind == "missing" else "basis"
                return json.dumps(
                    {
                        "issues": [issue]
                        if f"-{target_phase}-0" in phase
                        or (target_phase == "coverage" and "-coverage-" in phase)
                        else []
                    }
                )
            return json.dumps(followup(prompt, phase) if followup else {"issues": []})

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "skills/test/references"
            ref.mkdir(parents=True)
            for name in ("design-audit.md", "independent-review.md"):
                (ref / name).write_text("review rules")
            result = await generate_traceable_points(
                generation_input="frozen input",
                material={
                    "materialBlocks": [{"id": f"B{i}"} for i in range(1, 22)],
                    "questions": [],
                },
                scope={"testObjects": [], "impactAreas": [], "risks": [], "openQuestions": []},
                workspace=tmp,
                generate=generate,
                skill_name="test",
            )
        return json.loads(result), seen

    async def test_only_changed_basis_and_related_coverage_are_rechecked(self):
        def revise(value):
            value["testPoints"][0]["name"] += "边界"
            return value

        result, seen = await self.run_review(revise)
        self.assertEqual(result["reviewStatus"], "independent_reviewed")
        audits = {k: v for k, v in seen.items() if k.startswith("audit-1-")}
        self.assertEqual(len(audits), 3)
        for prompt in audits.values():
            self.assertNotIn("【模块20】验证登录", prompt)
        basis = next(v for k, v in audits.items() if "-basis-" in k)
        self.assertIn("【模块0】验证登录边界", basis)
        self.assertNotIn('"id": "P2"', basis)

    async def test_unchanged_revision_stops_and_preserves_issues(self):
        result, seen = await self.run_review(lambda value: value)
        self.assertEqual(result["reviewStatus"], "independent_review_failed")
        self.assertEqual(result["reviewIssues"][0]["targetId"], "P1")
        self.assertEqual(len([key for key in seen if key.startswith("correct")]), 1)
        self.assertFalse(any(key.startswith("audit-1-") for key in seen))

    async def test_deletion_is_reviewed_for_lost_coverage(self):
        def revise(value):
            value["testPoints"].pop(0)
            return value

        result, seen = await self.run_review(revise)
        self.assertEqual(result["reviewStatus"], "independent_reviewed")
        self.assertFalse(any(key.startswith("audit-1-basis") for key in seen))
        coverage = next(v for k, v in seen.items() if k.startswith("audit-1-coverage"))
        self.assertIn('"id": "P1"', coverage)
        self.assertIn("删除", coverage)
        self.assertNotIn("【模块20】验证登录", coverage)

    async def test_new_points_addressing_missing_issue_receive_basis_review(self):
        def revise(value):
            point = copy.deepcopy(value["testPoints"][0])
            point.update(id="P22", name="【模块0】验证新增边界")
            value["testPoints"].append(point)
            return value

        result, seen = await self.run_review(revise, issue_kind="missing")
        self.assertEqual(result["reviewStatus"], "independent_reviewed")
        basis = next(v for k, v in seen.items() if k.startswith("audit-1-basis"))
        self.assertIn('"id": "P22"', basis)
        self.assertNotIn('"id": "P21"', basis)

    async def test_out_of_scope_review_target_is_rejected(self):
        def revise(value):
            value["testPoints"][0]["name"] += "边界"
            return value

        def followup(prompt, phase):
            if "-coverage-" not in phase:
                return {"issues": []}
            return {
                "issues": [
                    {
                        "kind": "unsupported",
                        "targetType": "testPoint",
                        "targetId": "P21",
                        "issue": "越界意见",
                        "suggestion": "修改",
                        "materialBlockIds": ["B21"],
                        "testObjectIds": [],
                        "impactAreaIds": [],
                        "riskIds": [],
                        "materialQuestionIds": [],
                        "scopeQuestionIds": [],
                    }
                ]
            }

        with self.assertRaises(OutputValidationError):
            await self.run_review(revise, followup=followup)

    async def test_old_and_new_references_include_related_points_in_coverage_only(self):
        def revise(value):
            value["testPoints"][0]["materialBlockIds"] = ["B2"]
            return value

        result, seen = await self.run_review(revise)
        self.assertEqual(result["reviewStatus"], "independent_reviewed")
        coverage = next(v for k, v in seen.items() if k.startswith("audit-1-coverage"))
        self.assertIn("【模块1】验证登录", coverage)
        self.assertIn('"B1"', coverage)
        self.assertIn('"B2"', coverage)
        basis = next(v for k, v in seen.items() if k.startswith("audit-1-basis"))
        self.assertNotIn("【模块1】验证登录", basis)

    async def test_added_gap_is_reviewed_and_can_remain_unresolved(self):
        def revise(value):
            point = value["testPoints"][0]
            value["coverageGaps"] = [
                {
                    "id": "G1",
                    "description": "边界待确认",
                    "blockedCoverage": "边界用例",
                    **{k: v for k, v in point.items() if k.endswith("Ids")},
                }
            ]
            return value

        def followup(prompt, phase):
            if "-gaps-" not in phase:
                return {"issues": []}
            return {
                "issues": [
                    {
                        "kind": "classification",
                        "targetType": "coverageGap",
                        "targetId": "G1",
                        "issue": "缺口范围不准确",
                        "suggestion": "明确范围",
                        "materialBlockIds": ["B1"],
                        "testObjectIds": [],
                        "impactAreaIds": [],
                        "riskIds": [],
                        "materialQuestionIds": [],
                        "scopeQuestionIds": [],
                    }
                ]
            }

        result, seen = await self.run_review(revise, followup=followup)
        self.assertEqual(result["reviewStatus"], "independent_review_failed")
        self.assertEqual(result["reviewIssues"][0]["targetId"], "G1")
        gaps = next(v for k, v in seen.items() if k.startswith("audit-1-gaps"))
        self.assertIn("边界待确认", gaps)
        self.assertNotIn("【模块20】验证登录", gaps)
        self.assertNotIn("需要核对 B1 的边界", seen["correct-1"])

    async def test_reordering_points_does_not_restart_review(self):
        def revise(value):
            value["testPoints"].reverse()
            return value

        result, seen = await self.run_review(revise)
        self.assertEqual(result["reviewStatus"], "independent_review_failed")
        self.assertFalse(any(key.startswith("audit-1-") for key in seen))

    async def test_changed_gap_without_references_is_still_reviewed(self):
        def revise(value):
            value["coverageGaps"] = [
                {
                    "id": "G1",
                    "description": "缺少依据",
                    "blockedCoverage": "待确认范围",
                    **{k: [] for k in value["testPoints"][0] if k.endswith("Ids")},
                }
            ]
            return value

        result, seen = await self.run_review(revise)
        self.assertEqual(result["reviewStatus"], "independent_reviewed")
        gaps = next(v for k, v in seen.items() if k.startswith("audit-1-gaps"))
        entries = json.loads(gaps.split("【待审内容】\n")[1].split("\n\n")[0])
        self.assertEqual([entry["id"] for entry in entries], ["G1"])
