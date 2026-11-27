import json
import unittest
from unittest.mock import AsyncMock, patch

from testing_agent_ai_worker.tasks.functional_case_generate.case_planning import (
    _materialize_plan,
)
from testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches import (
    _build_model_batches,
    run_functional_detailed_case_batches,
)

from .fixtures import traceable_modules


def point(point_id, module, *, history=False):
    ref = {"stage": "historical_test_case_verification" if history else "case_names"}
    result = {"title": "验证导出", "module": module, "ref": {**ref, "pointId": point_id}}
    if history:
        result["impact"] = {"currentRule": "允许导出"}
    return result


def group(point_ids, module, finding=None):
    return {"pointIds": point_ids, "module": module, "findingId": finding, "reason": "验证依据"}


def finding(case_id, decision):
    return {"caseId": case_id, "decision": decision, "case": {"title": "旧用例"}}


class CasePlanningTests(unittest.IsolatedAsyncioTestCase):
    def test_planning_routes_only_new_scenarios_to_module_batches(self):
        points = {
            "P1": point("P1", "导出"),
            "P2": point("P2", "清洗"),
            "P3": point("point-1", None, history=True),
            "P4": point("point-2", None, history=True),
        }
        findings = {"F1": finding("C1", "reuse"), "F2": finding("C2", "modify")}
        plan = _materialize_plan(
            [group(["P1", "P3"], "导出", "F1"), group(["P4"], "导出", "F2"), group(["P2"], "清洗")],
            points,
            findings,
        )
        batches = _build_model_batches(json.dumps(traceable_modules("导出", "清洗")), plan)
        self.assertEqual([batch["model_name"] for batch in batches], ["清洗"])
        self.assertEqual([target["id"] for target in batches[0]["targets"]], ["P2"])
        self.assertEqual([entry["decision"] for entry in plan.findings], ["reuse", "modify"])
        self.assertEqual(len(plan.findings[0]["pointRefs"]), 2)

    def test_dropped_points_and_invalidated_case_reuse_are_rejected(self):
        points = {"P1": point("P1", "导出")}
        findings = {"F1": finding("C1", "reuse"), "F2": finding("C1", "invalidate")}
        with self.assertRaisesRegex(ValueError, "遗漏"):
            _materialize_plan([], points, findings)
        with self.assertRaisesRegex(ValueError, "只能匹配"):
            _materialize_plan([group(["P1"], "导出", "F1")], points, findings)

    async def test_all_reused_points_return_a_valid_empty_cases_list(self):
        plan = _materialize_plan(
            [group(["P1"], "导出", "F1")],
            {"P1": point("P1", "导出")},
            {"F1": finding("C1", "reuse")},
        )
        module_factory = AsyncMock(side_effect=AssertionError("无需调用模块生成"))
        with patch(
            "testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches.plan_case_generation",
            new=AsyncMock(return_value=plan),
        ):
            result = await run_functional_detailed_case_batches(
                requirement_analysis_json="{}",
                case_names_json=json.dumps(traceable_modules("导出")),
                session_key="s",
                skill_name="generate",
                source_text="{}",
                history_planning={},
                from_config=module_factory,
            )
        self.assertEqual(json.loads(result), {"cases": [], "historicalCaseFindings": plan.findings})
        module_factory.assert_not_called()
