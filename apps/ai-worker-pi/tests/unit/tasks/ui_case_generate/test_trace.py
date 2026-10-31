import unittest
from copy import deepcopy

from testing_agent_ai_worker_pi.tasks.ui_case_generate.trace import validate_trace
from tests.unit.tasks.ui_case_generate.test_completion import draft


def design():
    return dict(
        caseId="C1",
        steps=[
            dict(
                actions=[dict(actionId="A1", status="included", operation="click")],
                expectations=[dict(expectationId="E1", status="included", assertion="text_eq")],
            )
        ],
    )


class TraceTests(unittest.TestCase):
    def test_data_bound_steps_cover_reviewed_sources(self):
        validate_trace(draft(), design())

    def test_absent_assertion_maps_to_assert_hidden(self):
        case = draft()
        case["stepsJson"][1].update(keyword="assert_hidden")
        case["stepsJson"][1].pop("comparator")
        source = design()
        source["steps"][0]["expectations"][0]["assertion"] = "absent"
        validate_trace(case, source)

    def test_visible_or_manual_check_cannot_replace_text_comparison(self):
        case = draft()
        case["stepsJson"][1]["keyword"] = "assert_visible"
        case["stepsJson"][1].pop("comparator")
        with self.assertRaisesRegex(ValueError, "不能由"):
            validate_trace(case, design())
        case = draft()
        case["stepsJson"][1]["missingFields"] = [
            dict(fields=[], operation="人工核对", target="数据", value=None, reason="请人工确认")
        ]
        with self.assertRaisesRegex(ValueError, "空fields"):
            validate_trace(case, design())

    def test_excluded_goal_cannot_be_reintroduced(self):
        source = design()
        source["steps"][0]["expectations"][0]["status"] = "excluded"
        with self.assertRaisesRegex(ValueError, "已排除"):
            validate_trace(draft(), source)

    def test_missing_goal_requires_explicit_design_conflict(self):
        case = draft()
        case["stepsJson"].pop()
        with self.assertRaisesRegex(ValueError, "未覆盖"):
            validate_trace(case, design())
        case["designConflicts"] = [
            dict(
                sourceRefs=["expectation:E1"],
                reason="对象身份依赖运行中新ID，无法获取",
                requiredCapability="运行变量提取",
            )
        ]
        validate_trace(case, design())

    def test_setup_or_disabled_step_cannot_claim_business_coverage(self):
        case = draft()
        case["stepsJson"][1]["purpose"] = "setup"
        with self.assertRaisesRegex(ValueError, "不能降为"):
            validate_trace(case, design())
        case = deepcopy(draft())
        case["stepsJson"][1]["enabled"] = False
        with self.assertRaisesRegex(ValueError, "不能禁用"):
            validate_trace(case, design())

    def test_navigation_can_use_application_link_with_preserved_route_context(self):
        source = design()
        source["steps"][0]["actions"][0]["operation"] = "navigate"
        validate_trace(draft(), source)

    def test_refresh_alone_does_not_cover_observation(self):
        source = design()
        source["steps"][0]["actions"][0]["operation"] = "observe"
        case = draft()
        with self.assertRaisesRegex(ValueError, "未覆盖"):
            validate_trace(case, source)
        case["stepsJson"][1]["sourceRefs"].append("action:A1")
        validate_trace(case, source)
